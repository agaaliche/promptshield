/** Dialog shown when one or more file uploads fail. */

import { useTranslation } from "react-i18next";
import { AlertTriangle, RefreshCw, X } from "../icons";
import { useAppStore } from "../store";
import { getFailedFiles, clearFailedFileRefs } from "../hooks/useDocumentUpload";
import { Z_MODAL } from "../zIndex";

const DISMISS_ANIMATION_MS = 400;

export default function UploadErrorDialog({ onRetry }: { onRetry?: (files: File[]) => void }) {
  const { t } = useTranslation();
  const show = useAppStore((s) => s.showUploadErrorDialog);
  const uploadQueue = useAppStore((s) => s.uploadQueue);
  const setShowUploadErrorDialog = useAppStore((s) => s.setShowUploadErrorDialog);
  const setDismissingErrorUploads = useAppStore((s) => s.setDismissingErrorUploads);
  const removeErrorUploads = useAppStore((s) => s.removeErrorUploads);

  if (!show) return null;

  const errorItems = uploadQueue.filter((u) => u.status === "error");
  if (errorItems.length === 0) return null;

  const handleClose = () => {
    setShowUploadErrorDialog(false);
    clearFailedFileRefs();
    // Trigger fade-out animation on sidebar error items
    setDismissingErrorUploads(true);
    setTimeout(() => {
      removeErrorUploads();
      setDismissingErrorUploads(false);
    }, DISMISS_ANIMATION_MS);
  };

  const handleRetry = () => {
    const files = getFailedFiles();
    clearFailedFileRefs();
    setShowUploadErrorDialog(false);
    // Remove error items from queue before re-queuing
    removeErrorUploads();
    if (files.length > 0 && onRetry) {
      onRetry(files);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={styles.overlay}
      onClick={handleClose}
    >
      <div style={styles.card} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <AlertTriangle size={20} style={{ color: "#f44336", flexShrink: 0 }} />
          <span style={styles.title}>
            {errorItems.length === 1
              ? t("upload.uploadFailed")
              : t("upload.nUploadsFailed", { count: errorItems.length })}
          </span>
          <button style={styles.closeBtn} onClick={handleClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* File list */}
        <div style={styles.list}>
          {errorItems.map((item) => (
            <div key={item.id} style={styles.row}>
              <span style={styles.fileName}>{item.name}</span>
              <span style={styles.errorMsg}>{item.error || t("upload.unknownError")}</span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={styles.footer}>
          {onRetry && (
            <button style={styles.retryBtn} onClick={handleRetry}>
              <RefreshCw size={13} style={{ marginRight: 6 }} />
              {errorItems.length === 1 ? t("common.retry") : t("upload.retryN", { count: errorItems.length })}
            </button>
          )}
          <button style={styles.okBtn} onClick={handleClose}>
            {t("common.dismiss")}
          </button>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(0,0,0,0.6)",
    zIndex: Z_MODAL,
  },
  card: {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    padding: 24,
    maxWidth: 440,
    width: "90%",
    boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  title: {
    flex: 1,
    fontSize: 15,
    fontWeight: 600,
    color: "var(--text-primary)",
  },
  closeBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "var(--text-muted)",
    padding: 4,
    borderRadius: 4,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    maxHeight: 200,
    overflowY: "auto",
  },
  row: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "6px 8px",
    background: "rgba(244,67,54,0.08)",
    borderRadius: 6,
    border: "1px solid rgba(244,67,54,0.2)",
  },
  fileName: {
    fontSize: 13,
    fontWeight: 500,
    color: "var(--text-primary)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  errorMsg: {
    fontSize: 11,
    color: "var(--text-muted)",
  },
  footer: {
    display: "flex",
    justifyContent: "flex-end",
    gap: 8,
  },
  retryBtn: {
    background: "transparent",
    color: "var(--accent-primary)",
    border: "1px solid var(--accent-primary)",
    borderRadius: 6,
    padding: "6px 16px",
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
  },
  okBtn: {
    background: "var(--accent-primary)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    padding: "6px 24px",
    fontSize: 13,
    fontWeight: 500,
    cursor: "pointer",
  },
};
