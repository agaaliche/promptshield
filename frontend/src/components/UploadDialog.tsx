/** Upload dialog — drag & drop overlay that appears on top of the document viewer. */

import { useCallback, useRef, useState } from "react";
import { Upload, X, FolderUp } from "lucide-react";
import { useUploadStore, useUIStore } from "../store";
import { useDocumentUpload, ACCEPTED_FILE_TYPES } from "../hooks/useDocumentUpload";
import { Z_UPLOAD_DIALOG } from "../zIndex";

const ACCEPT = ACCEPTED_FILE_TYPES;

export default function UploadDialog() {
  const { showUploadDialog, setShowUploadDialog } = useUploadStore();
  const { isProcessing } = useUIStore();

  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const { handleFiles } = useDocumentUpload({
    onBeforeUpload: () => setShowUploadDialog(false),
    verboseLoadingMessages: true,
  });

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const onBackdropClick = useCallback(() => {
    setShowUploadDialog(false);
  }, [setShowUploadDialog]);

  if (!showUploadDialog) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Upload documents"
      style={styles.backdrop}
      onClick={onBackdropClick}
    >
      <div style={styles.dialog} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <Upload size={18} style={{ color: "var(--accent-primary)" }} />
          <span style={styles.headerTitle}>Upload Documents</span>
          <button
            className="btn-ghost btn-sm"
            onClick={() => setShowUploadDialog(false)}
            style={{ padding: 4 }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Drop zone */}
        <div style={styles.body}>
          <div
            style={{
              ...styles.dropzone,
              ...(dragging ? styles.dropzoneActive : {}),
              ...(isProcessing ? styles.dropzoneDisabled : {}),
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => !isProcessing && fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPT}
              multiple
              style={{ display: "none" }}
              onChange={(e) => {
                handleFiles(e.target.files);
                if (e.target) e.target.value = "";
              }}
            />
            <input
              ref={folderRef}
              type="file"
              // @ts-expect-error webkitdirectory is non-standard
              webkitdirectory=""
              multiple
              style={{ display: "none" }}
              onChange={(e) => {
                handleFiles(e.target.files);
                if (e.target) e.target.value = "";
              }}
            />

            {isProcessing ? (
              <div style={styles.processingContent}>
                <div style={styles.spinner} />
                <p style={styles.processingText}>Processing documents...</p>
              </div>
            ) : (
              <>
                <Upload
                  size={44}
                  style={{ color: "var(--accent-primary)", marginBottom: 14 }}
                />
                <p style={styles.dropText}>
                  Drag & drop files here, or click to browse
                </p>
                <p style={styles.formatText}>
                  Supports: PDF, DOCX, XLSX, PPTX, JPG, PNG, TIFF, BMP
                </p>
                <button
                  className="btn-ghost btn-sm"
                  style={styles.folderBtn}
                  onClick={(e) => {
                    e.stopPropagation();
                    folderRef.current?.click();
                  }}
                >
                  <FolderUp size={14} /> Upload folder
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0, 0, 0, 0.55)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: Z_UPLOAD_DIALOG,
  },
  dialog: {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    width: 520,
    maxWidth: "90vw",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 12px 48px rgba(0, 0, 0, 0.5)",
    animation: "uploadDialogIn 0.18s ease-out",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "14px 16px",
    borderBottom: "1px solid var(--border-color)",
  },
  headerTitle: {
    flex: 1,
    fontSize: 15,
    fontWeight: 600,
    color: "var(--text-primary)",
  },
  body: {
    padding: 20,
  },
  dropzone: {
    border: "2px dashed var(--border-color)",
    borderRadius: 10,
    padding: "44px 24px",
    textAlign: "center" as const,
    cursor: "pointer",
    transition: "all 0.2s ease",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
  },
  dropzoneActive: {
    borderColor: "var(--accent-primary)",
    background: "rgba(74, 158, 255, 0.06)",
  },
  dropzoneDisabled: {
    cursor: "wait",
    opacity: 0.7,
  },
  dropText: { fontSize: 15, fontWeight: 500, marginBottom: 8 },
  formatText: { fontSize: 12, color: "var(--text-muted)", marginBottom: 16 },
  folderBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "7px 14px",
    fontSize: 12,
    border: "1px solid var(--border-color)",
    borderRadius: 6,
  },
  processingContent: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
  },
  processingText: { color: "var(--text-secondary)" },
  spinner: {
    width: 36,
    height: 36,
    border: "3px solid var(--border-color)",
    borderTopColor: "var(--accent-primary)",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
};
