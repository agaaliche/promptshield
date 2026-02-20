/** Upload view — drag & drop or file picker for document upload. */

import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Upload, AlertCircle, FolderUp } from "../icons";
import { useUIStore } from "../store";
import { useDocumentUpload, ACCEPTED_FILE_TYPES } from "../hooks/useDocumentUpload";

const ACCEPT = ACCEPTED_FILE_TYPES;

export default function UploadView() {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const { isProcessing } = useUIStore();
  const { t } = useTranslation();

  const { handleFiles } = useDocumentUpload({
    onBeforeUpload: () => setError(""),
    onFileError: (e) => setError(e.message || "Upload failed"),
  });

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>prompt<span style={{ color: 'var(--accent-primary)' }}>{t("common.shield")}</span></h1>
        <p style={styles.subtitle}>
          {t("upload.subtitle")}
        </p>
      </div>

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
          onChange={(e) => { handleFiles(e.target.files); if (e.target) e.target.value = ""; }}
        />
        <input
          ref={folderRef}
          type="file"
          // @ts-expect-error webkitdirectory is non-standard
          webkitdirectory=""
          multiple
          style={{ display: "none" }}
          onChange={(e) => { handleFiles(e.target.files); if (e.target) e.target.value = ""; }}
        />

        {isProcessing ? (
          <div style={styles.processingContent}>
            <div style={styles.spinner} />
            <p style={styles.processingText}>{t("upload.processing")}</p>
          </div>
        ) : (
          <>
            <Upload size={48} style={{ color: "var(--accent-primary)", marginBottom: 16 }} />
            <p style={styles.dropText}>
              {t("upload.dragDrop")}
            </p>
            <p style={styles.formatText}>
              {t("upload.supportedFormats")}
            </p>
            <button
              style={styles.folderBtn}
              onClick={(e) => { e.stopPropagation(); folderRef.current?.click(); }}
            >
              <FolderUp size={16} /> {t("upload.uploadFolder")}
            </button>
          </>
        )}
      </div>

      {error && (
        <div style={styles.error}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div style={styles.features}>
        <FeatureCard
          icon="🔒"
          title={t("upload.featureOffline")}
          desc={t("upload.featureOfflineDesc")}
        />
        <FeatureCard
          icon="🤖"
          title={t("upload.featureAI")}
          desc={t("upload.featureAIDesc")}
        />
        <FeatureCard
          icon="🔑"
          title={t("upload.featureTokens")}
          desc={t("upload.featureTokensDesc")}
        />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={styles.featureCard}>
      <span style={{ fontSize: 24 }}>{icon}</span>
      <h3 style={{ fontSize: 14, fontWeight: 600 }}>{title}</h3>
      <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{desc}</p>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    padding: 40,
    gap: 24,
  },
  header: { textAlign: "center" },
  title: { fontSize: 32, fontWeight: 500, marginBottom: 8, letterSpacing: "-0.5px" },
  subtitle: { color: "var(--text-secondary)", fontSize: 15 },
  dropzone: {
    width: "100%",
    maxWidth: 560,
    border: "2px dashed var(--border-color)",
    borderRadius: 12,
    padding: 48,
    textAlign: "center" as const,
    cursor: "pointer",
    transition: "all 0.2s ease",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
  },
  dropzoneActive: {
    borderColor: "var(--accent-primary)",
    background: "rgba(74, 158, 255, 0.05)",
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
    padding: "8px 16px",
    fontSize: 13,
    border: "1px solid var(--border-color)",
    borderRadius: 6,
    background: "transparent",
    color: "var(--text-secondary)",
    cursor: "pointer",
    transition: "all 0.15s ease",
  },
  processingContent: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
  },
  processingText: { color: "var(--text-secondary)" },
  spinner: {
    width: 40,
    height: 40,
    border: "3px solid var(--border-color)",
    borderTopColor: "var(--accent-primary)",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  error: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    color: "var(--accent-danger)",
    fontSize: 13,
    padding: "8px 16px",
    background: "rgba(244, 67, 54, 0.1)",
    borderRadius: 6,
  },
  features: {
    display: "flex",
    gap: 16,
    marginTop: 24,
    maxWidth: 700,
  },
  featureCard: {
    flex: 1,
    background: "var(--bg-surface)",
    borderRadius: 8,
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 8,
    textAlign: "center" as const,
  },
};
