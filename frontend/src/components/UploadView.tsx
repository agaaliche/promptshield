/** Upload view — drag & drop or file picker for document upload. */

import { useCallback, useRef, useState } from "react";
import { Upload, FileText, AlertCircle } from "lucide-react";
import { uploadDocument, getDocument, detectPII } from "../api";
import { useAppStore } from "../store";
import type { DocumentInfo } from "../types";

const ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.tiff,.tif,.bmp,.webp,.docx,.xlsx,.pptx,.doc,.xls,.ppt";

export default function UploadView() {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const {
    setActiveDocId,
    setRegions,
    setCurrentView,
    setIsProcessing,
    setStatusMessage,
    addDocument,
    isProcessing,
  } = useAppStore();

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      setError("");
      setIsProcessing(true);

      try {
        const file = files[0]; // Process one file at a time for now
        setStatusMessage(`Uploading ${file.name}...`);

        const uploadRes = await uploadDocument(file);
        setStatusMessage(`Processing ${file.name} (${uploadRes.page_count} pages)...`);

        // Fetch full document data
        const doc = await getDocument(uploadRes.doc_id);
        addDocument(doc);
        setActiveDocId(doc.doc_id);

        // Run PII detection
        setStatusMessage("Detecting PII...");
        const detection = await detectPII(doc.doc_id);
        setRegions(detection.regions);

        setStatusMessage(
          `Found ${detection.total_regions} potential PII region(s)`
        );
        setCurrentView("viewer");
      } catch (e: any) {
        setError(e.message || "Upload failed");
        setStatusMessage("");
      } finally {
        setIsProcessing(false);
      }
    },
    [setActiveDocId, setRegions, setCurrentView, setIsProcessing, setStatusMessage, addDocument]
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
        <h1 style={styles.title}>Document Anonymizer</h1>
        <p style={styles.subtitle}>
          Upload a document to detect and anonymize personal information
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
          style={{ display: "none" }}
          onChange={(e) => handleFiles(e.target.files)}
        />

        {isProcessing ? (
          <div style={styles.processingContent}>
            <div style={styles.spinner} />
            <p style={styles.processingText}>Processing document...</p>
          </div>
        ) : (
          <>
            <Upload size={48} style={{ color: "var(--accent-primary)", marginBottom: 16 }} />
            <p style={styles.dropText}>
              Drag & drop a document here, or click to browse
            </p>
            <p style={styles.formatText}>
              Supports: PDF, DOCX, XLSX, PPTX, JPG, PNG, TIFF, BMP
            </p>
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
  title: { fontSize: 28, fontWeight: 700, marginBottom: 8 },
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
  formatText: { fontSize: 12, color: "var(--text-muted)" },
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
