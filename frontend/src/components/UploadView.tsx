/** Upload view — drag & drop or file picker for document upload. */

import { useCallback, useRef, useState } from "react";
import { Upload, AlertCircle, FolderUp } from "lucide-react";
import { uploadDocument, getDocument, detectPII } from "../api";
import { resolveAllOverlaps } from "../regionUtils";
import { useAppStore } from "../store";
import type { UploadItem } from "../types";

const ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.docx,.xlsx,.pptx,.doc,.xls,.ppt";

export default function UploadView() {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const {
    setActiveDocId,
    setRegions,
    setCurrentView,
    addDocument,
    updateDocument,
    isProcessing,
    addToUploadQueue,
    updateUploadItem,
    clearCompletedUploads,
    setDocDetecting,
    setDocLoadingMessage,
  } = useAppStore();

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const fileArray = Array.from(files);
      setError("");

      // Build queue items — they appear immediately in the Sidebar accordion
      const items: { file: File; item: UploadItem }[] = [];
      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i];
        const relPath = (file as any).webkitRelativePath || "";
        const parentPath = relPath ? relPath.substring(0, relPath.lastIndexOf("/")) : "";
        const id = `upload-${Date.now()}-${i}`;
        items.push({
          file,
          item: { id, name: file.name, parentPath, status: "queued", progress: 0 },
        });
      }

      // Add to store queue — Sidebar will show them immediately
      addToUploadQueue(items.map((i) => i.item));
      // Switch to viewer so the Sidebar accordion is visible
      setCurrentView("viewer");

      // Process sequentially
      for (const { file, item } of items) {
        try {
          updateUploadItem(item.id, { status: "uploading", progress: 30 });
          const uploadRes = await uploadDocument(file);

          updateUploadItem(item.id, { progress: 50 });
          const doc = await getDocument(uploadRes.doc_id);
          addDocument(doc);
          // Set detecting BEFORE activeDocId so the progress dialog shows immediately
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
          updateUploadItem(item.id, { status: "error", error: e.message || "Failed" });
          setError(e.message || "Upload failed");
        }
      }

      clearCompletedUploads();
    },
    [setActiveDocId, setRegions, setCurrentView, addDocument, updateDocument, addToUploadQueue, updateUploadItem, clearCompletedUploads, setDocDetecting, setDocLoadingMessage]
  );

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
        <h1 style={styles.title}>prompt<span style={{ color: 'var(--accent-primary)' }}>Shield</span></h1>
        <p style={styles.subtitle}>
          Upload documents to detect and anonymize personal information
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
            <p style={styles.processingText}>Processing documents...</p>
          </div>
        ) : (
          <>
            <Upload size={48} style={{ color: "var(--accent-primary)", marginBottom: 16 }} />
            <p style={styles.dropText}>
              Drag & drop files here, or click to browse
            </p>
            <p style={styles.formatText}>
              Supports: PDF, DOCX, XLSX, PPTX, JPG, PNG, TIFF, BMP
            </p>
            <button
              style={styles.folderBtn}
              onClick={(e) => { e.stopPropagation(); folderRef.current?.click(); }}
            >
              <FolderUp size={16} /> Upload folder
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
          title="Fully Offline"
          desc="All processing happens locally. Your data never leaves your machine."
        />
        <FeatureCard
          icon="🤖"
          title="AI-Powered Detection"
          desc="Hybrid regex + NER + LLM pipeline for comprehensive PII detection."
        />
        <FeatureCard
          icon="🔑"
          title="Reversible Tokens"
          desc="Tokenize PII for AI workflows. De-tokenize responses to restore originals."
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
