/**
 * Shared upload-detect-resolve pipeline hook (M5).
 *
 * Extracted from UploadView and Sidebar to eliminate the duplicated
 * ~55-line handleFiles callback.
 */

import { useCallback } from "react";
import { uploadDocument, getDocument, detectPII } from "../api";
import { resolveAllOverlaps } from "../regionUtils";
import { useAppStore } from "../store";
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
export function useDocumentUpload(options: UseDocumentUploadOptions = {}) {
  const {
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
  } = useAppStore();

  const { onBeforeUpload, onFileError, verboseLoadingMessages = false } = options;

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const fileArray = Array.from(files);

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
          updateUploadItem(item.id, { status: "uploading", progress: 30 });
          if (verboseLoadingMessages) setDocLoadingMessage("Uploading document\u2026");

          const uploadRes = await uploadDocument(file);

          updateUploadItem(item.id, { progress: 50 });
          if (verboseLoadingMessages) setDocLoadingMessage("Processing pages\u2026");

          const doc = await getDocument(uploadRes.doc_id);
          addDocument(doc);

          setDocDetecting(true);
          setDocLoadingMessage("Analyzing document for PII entities\u2026");
          setActiveDocId(doc.doc_id);

          updateUploadItem(item.id, { status: "detecting", progress: 70 });
          const detection = await detectPII(doc.doc_id);
          const resolved = resolveAllOverlaps(detection.regions);
          setRegions(resolved);
          updateDocument(doc.doc_id, { regions: resolved });

          setDocDetecting(false);
          setDocLoadingMessage("");
          updateUploadItem(item.id, { status: "done", progress: 100 });
        } catch (e: any) {
          setDocDetecting(false);
          setDocLoadingMessage("");
          updateUploadItem(item.id, {
            status: "error",
            error: e.message || "Failed",
          });
          onFileError?.(e, file.name);
        }
      }

      clearCompletedUploads();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      onBeforeUpload,
      onFileError,
      verboseLoadingMessages,
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
    ],
  );

  return { handleFiles };
}
