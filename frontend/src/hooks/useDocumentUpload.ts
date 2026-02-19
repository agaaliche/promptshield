/**
 * Shared upload-detect-resolve pipeline hook (M5).
 *
 * Extracted from UploadView and Sidebar to eliminate the duplicated
 * ~55-line handleFiles callback.
 */

import { useCallback } from "react";
import { uploadDocument, getDocument, getUploadProgress, deleteDocument } from "../api";
import { toErrorMessage } from "../errorUtils";
import { useAppStore, useDocumentStore, useUIStore, useUploadStore, useDocLoadingStore } from "../store";
import type { UploadItem } from "../types";

/** Accepted file types for the document upload input. */
export const ACCEPTED_FILE_TYPES =
  ".pdf,.jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.docx,.xlsx,.pptx,.doc,.xls,.ppt";

/**
 * Module-level map: upload-item ID → original File object.
 * Kept outside React so retry can access the File after an error.
 * Entries are cleaned up when uploads succeed or errors are dismissed.
 */
const _pendingFiles = new Map<string, File>();

/** Return File objects for all currently-errored upload items. */
export function getFailedFiles(): File[] {
  const queue = useAppStore.getState().uploadQueue;
  const files: File[] = [];
  for (const item of queue) {
    if (item.status === "error") {
      const f = _pendingFiles.get(item.id);
      if (f) files.push(f);
    }
  }
  return files;
}

/** Remove File refs for errored items (call after dismiss / retry). */
export function clearFailedFileRefs(): void {
  const queue = useAppStore.getState().uploadQueue;
  for (const item of queue) {
    if (item.status === "error") _pendingFiles.delete(item.id);
  }
}

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
  const { setActiveDocId, addDocument } = useDocumentStore();
  const { setCurrentView, setStatusMessage } = useUIStore();
  const { addToUploadQueue, updateUploadItem, clearCompletedUploads, setShowUploadErrorDialog } = useUploadStore();
  const { setDocLoadingMessage, setUploadProgressId, setUploadProgressDocName, setUploadProgressPhase, setUploadProgressDocId } = useDocLoadingStore();

  const documents = useAppStore((s) => s.documents);
  const setDocuments = useAppStore((s) => s.setDocuments);

  const { onBeforeUpload, onFileError, verboseLoadingMessages = false } = options;

  const handleFiles = useCallback(
    async (files: FileList | File[] | null) => {
      if (!files || files.length === 0) return;
      const fileArray = Array.from(files);

      // Deduplicate within the batch: if multiple files have the same name,
      // keep only the last occurrence (it overwrites the earlier ones).
      const seenNames = new Map<string, number>();
      for (let i = 0; i < fileArray.length; i++) {
        seenNames.set(fileArray[i].name, i);
      }
      const dedupedFiles = fileArray.filter((_, i) =>
        [...seenNames.values()].includes(i)
      );

      // Warn if total document count will exceed export limit
      const totalAfter = documents.length + dedupedFiles.length;
      if (totalAfter > MAX_EXPORT_DOCS) {
        setStatusMessage(
          `Warning: You will have ${totalAfter} documents, but only ${MAX_EXPORT_DOCS} can be exported at once.`
        );
      }

      onBeforeUpload?.();

      // Build queue items
      const items: { file: File; item: UploadItem }[] = [];
      for (let i = 0; i < dedupedFiles.length; i++) {
        const file = dedupedFiles[i];
        const relPath = (file as any).webkitRelativePath || "";
        const parentPath = relPath
          ? relPath.substring(0, relPath.lastIndexOf("/"))
          : "";
        const id = `upload-${Date.now()}-${i}`;
        _pendingFiles.set(id, file);
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

          // ── Deduplicate: remove existing document with the same filename ──
          const currentDocs = useAppStore.getState().documents;
          const existing = currentDocs.find(
            (d) => d.original_filename === file.name
          );
          if (existing) {
            try {
              await deleteDocument(existing.doc_id);
              setDocuments(
                useAppStore.getState().documents.filter(
                  (d) => d.doc_id !== existing.doc_id
                )
              );
            } catch {
              // non-fatal — the new upload will still proceed
            }
          }

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

          setActiveDocId(doc.doc_id);

          // Upload complete — detection is deferred until user uses Detect menu
          setUploadProgressPhase("done");
          updateUploadItem(item.id, { status: "done", progress: 100 });
          _pendingFiles.delete(item.id);
        } catch (e: unknown) {
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
      setCurrentView,
      addDocument,
      addToUploadQueue,
      updateUploadItem,
      clearCompletedUploads,
      setDocLoadingMessage,
      setStatusMessage,
      setShowUploadErrorDialog,
      setUploadProgressId,
      setUploadProgressDocName,
      setUploadProgressPhase,
      setDocuments,
    ],
  );

  return { handleFiles };
}
