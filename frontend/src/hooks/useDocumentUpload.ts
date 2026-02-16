/**
 * Shared upload-detect-resolve pipeline hook (M5).
 *
 * Extracted from UploadView and Sidebar to eliminate the duplicated
 * ~55-line handleFiles callback.
 */

import { useCallback } from "react";
import { uploadDocument, getDocument, detectPII, getUploadProgress } from "../api";
import { resolveAllOverlaps } from "../regionUtils";
import { toErrorMessage } from "../errorUtils";
import { useAppStore, useDocumentStore, useRegionStore, useUIStore, useUploadStore, useDocLoadingStore } from "../store";
import type { UploadItem } from "../types";

/** Accepted file types for the document upload input. */
export const ACCEPTED_FILE_TYPES =
  ".pdf,.jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.docx,.xlsx,.pptx,.doc,.xls,.ppt";

export interface UseDocumentUploadOptions {
  /** Called before the upload loop starts (e.g. close dialogs, switch view). */
  onBeforeUpload?: () => void;
  /** Called when a single file fails. Return value is ignored. */
  onFileError?: (error: Error, fileName: string) => void;
  /** If true, set intermediate loading messages during upload/page steps. */
  verboseLoadingMessages?: boolean;
}

/**
 * Returns a `handleFiles` callback that runs the full
 * upload → detect → resolve pipeline for every file.
 */
/** Maximum documents allowed for export in a single batch. */
const MAX_EXPORT_DOCS = 50;

export function useDocumentUpload(options: UseDocumentUploadOptions = {}) {
  const { setActiveDocId, addDocument, updateDocument } = useDocumentStore();
  const { setRegions } = useRegionStore();
  const { setCurrentView, setStatusMessage } = useUIStore();
  const { addToUploadQueue, updateUploadItem, clearCompletedUploads, setShowUploadErrorDialog } = useUploadStore();
  const { setDocDetecting, setDocLoadingMessage, setUploadProgressId, setUploadProgressDocId, setUploadProgressDocName, setUploadProgressPhase } = useDocLoadingStore();

  const documents = useAppStore((s) => s.documents);

  const { onBeforeUpload, onFileError, verboseLoadingMessages = false } = options;

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const fileArray = Array.from(files);

      // Warn if total document count will exceed export limit
      const totalAfter = documents.length + fileArray.length;
      if (totalAfter > MAX_EXPORT_DOCS) {
        setStatusMessage(
          `Warning: You will have ${totalAfter} documents, but only ${MAX_EXPORT_DOCS} can be exported at once.`
        );
      }

      onBeforeUpload?.();

      // Build queue items
      const items: { file: File; item: UploadItem }[] = [];
      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i];
        const relPath = (file as any).webkitRelativePath || "";
        const parentPath = relPath
          ? relPath.substring(0, relPath.lastIndexOf("/"))
          : "";
        const id = `upload-${Date.now()}-${i}`;
        items.push({
          file,
          item: { id, name: file.name, parentPath, status: "queued", progress: 0 },
        });
      }

      addToUploadQueue(items.map((i) => i.item));
      setCurrentView("viewer");

      // Process sequentially
      for (const { file, item } of items) {
        try {
          updateUploadItem(item.id, { status: "uploading", progress: 5 });
          if (verboseLoadingMessages) setDocLoadingMessage("Uploading document\u2026");

          // Generate a unique progress ID and start polling OCR progress
          const progressId = `progress-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

          // Set up the upload progress dialog
          setUploadProgressId(progressId);
          setUploadProgressDocName(file.name);
          setUploadProgressPhase("uploading");
          setUploadProgressDocId(null);

          let pollTimer: ReturnType<typeof setInterval> | null = null;

          // Start background polling for OCR progress
          pollTimer = setInterval(async () => {
            try {
              const info = await getUploadProgress(progressId);
              if (info.status === "processing") {
                let pct: number;
                if (info.phase === "starting") {
                  pct = 10;
                } else if (info.phase === "extracting") {
                  pct = info.total_pages > 0
                    ? 10 + Math.round((info.current_page / info.total_pages) * 30)
                    : 15;
                } else if (info.phase === "ocr") {
                  pct = info.ocr_pages_total > 0
                    ? 40 + Math.round((info.ocr_pages_done / info.ocr_pages_total) * 40)
                    : 45;
                } else {
                  pct = 80;
                }
                updateUploadItem(item.id, {
                  progress: pct,
                  ocrPhase: info.phase as "starting" | "extracting" | "ocr" | "complete",
                  ocrMessage: info.message,
                });
                if (verboseLoadingMessages) setDocLoadingMessage(info.message || "Processing pages\u2026");
              }
            } catch {
              // polling errors are non-fatal
            }
          }, 400);

          let uploadRes;
          try {
            uploadRes = await uploadDocument(file, progressId);
          } finally {
            if (pollTimer) clearInterval(pollTimer);
          }

          updateUploadItem(item.id, { progress: 85, ocrPhase: "complete", ocrMessage: "" });
          if (verboseLoadingMessages) setDocLoadingMessage("Processing pages\u2026");

          const doc = await getDocument(uploadRes.doc_id);
          addDocument(doc);

          setDocDetecting(true);
          setDocLoadingMessage("Analyzing document for PII entities\u2026");
          setActiveDocId(doc.doc_id);

          // Update progress dialog for detection phase
          setUploadProgressDocId(doc.doc_id);
          setUploadProgressPhase("detecting");

          updateUploadItem(item.id, { status: "detecting", progress: 90, ocrPhase: undefined, ocrMessage: undefined });
          const detection = await detectPII(doc.doc_id);
          const resolved = resolveAllOverlaps(detection.regions);
          setRegions(resolved);
          updateDocument(doc.doc_id, { regions: resolved });

          setDocDetecting(false);
          setDocLoadingMessage("");
          setUploadProgressPhase("done");
          updateUploadItem(item.id, { status: "done", progress: 100 });
        } catch (e: unknown) {
          setDocDetecting(false);
          setDocLoadingMessage("");
          setUploadProgressPhase("error");
          updateUploadItem(item.id, {
            status: "error",
            error: toErrorMessage(e) || "Failed",
          });
          onFileError?.(e instanceof Error ? e : new Error(toErrorMessage(e)), file.name);
        }
      }

      clearCompletedUploads();

      // Show error dialog if any uploads failed
      const hasErrors = items.some(({ item }) =>
        useAppStore.getState().uploadQueue.find((u) => u.id === item.id)?.status === "error"
      );
      if (hasErrors) {
        setShowUploadErrorDialog(true);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      onBeforeUpload,
      onFileError,
      verboseLoadingMessages,
      documents.length,
      setActiveDocId,
      setRegions,
      setCurrentView,
      addDocument,
      updateDocument,
      addToUploadQueue,
      updateUploadItem,
      clearCompletedUploads,
      setDocDetecting,
      setDocLoadingMessage,
      setStatusMessage,
      setShowUploadErrorDialog,
      setUploadProgressId,
      setUploadProgressDocId,
      setUploadProgressDocName,
      setUploadProgressPhase,
    ],
  );

  return { handleFiles };
}
