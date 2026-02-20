/**
 * UploadProgressDialog — unified progress dialog for document upload pipeline.
 *
 * Shows two sequential phases:
 *   1. Extraction (page rendering via PDFium)
 *   2. OCR (Tesseract per-page, if needed)
 *
 * Detection is deferred until the user explicitly uses the Detect menu.
 *
 * Polls getUploadProgress from the backend.
 */

import { useEffect, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Clock,
  ScanSearch,
} from "../icons";
import { getUploadProgress } from "../api";
import type { UploadProgressInfo } from "../api";
import { Z_MODAL } from "../zIndex";

interface Props {
  /** Upload progress tracking ID (passed to uploadDocument). */
  uploadProgressId: string | null;
  /** Document ID (available after upload completes, used for detection polling). */
  docId: string | null;
  /** Document name for display. */
  docName: string;
  /** Current pipeline phase from the hook. */
  phase: "uploading" | "done" | "error";
  /** Whether visible. */
  visible: boolean;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

/** Phase config for the two-step indicator. */
const PHASE_LABEL_KEYS = [
  { key: "extracting", labelKey: "uploadProgress.phaseExtract", icon: FileText },
  { key: "ocr", labelKey: "uploadProgress.phaseOCR", icon: ScanSearch },
] as const;

export default function UploadProgressDialog({
  uploadProgressId,
  docId,
  docName,
  phase,
  visible,
}: Props) {
  const { t } = useTranslation();
  const [uploadInfo, setUploadInfo] = useState<UploadProgressInfo | null>(null);
  const uploadPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(Date.now());

  // Track elapsed locally
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!visible) return;
    startTimeRef.current = Date.now();
    const t = setInterval(() => setElapsed((Date.now() - startTimeRef.current) / 1000), 500);
    return () => clearInterval(t);
  }, [visible]);

  // Poll upload progress
  useEffect(() => {
    if (!visible || !uploadProgressId || phase === "done" || phase === "error") {
      return;
    }
    const poll = async () => {
      try {
        const info = await getUploadProgress(uploadProgressId);
        setUploadInfo(info);
      } catch {
        // ignore
      }
    };
    poll();
    uploadPollRef.current = setInterval(poll, 500);
    return () => {
      if (uploadPollRef.current) clearInterval(uploadPollRef.current);
    };
  }, [visible, uploadProgressId, phase]);

  // Reset state when dialog opens for a new file
  useEffect(() => {
    if (visible) {
      setUploadInfo(null);
    }
  }, [visible, uploadProgressId]);

  if (!visible) return null;

  // Determine which of the 2 phases is active
  const uploadPhase = uploadInfo?.phase ?? "starting";
  const isUploading = phase === "uploading";
  const isDone = phase === "done";
  const isError = phase === "error";

  // Compute active phase index (0=extracting, 1=ocr)
  let activePhaseIdx = 0;
  if (isUploading) {
    if (uploadPhase === "ocr") activePhaseIdx = 1;
    else activePhaseIdx = 0;
  } else if (isDone) {
    activePhaseIdx = PHASE_LABEL_KEYS.length; // all done
  }

  // Overall percentage (0-100 across 2 phases: each gets ~50%)
  let overallPct = 0;
  if (isUploading) {
    if (uploadPhase === "starting") {
      overallPct = 2;
    } else if (uploadPhase === "extracting") {
      const pagePct = uploadInfo && uploadInfo.total_pages > 0
        ? uploadInfo.current_page / uploadInfo.total_pages
        : 0;
      overallPct = Math.round(2 + pagePct * 46); // 2-48%
    } else if (uploadPhase === "ocr") {
      const ocrPct = uploadInfo && uploadInfo.ocr_pages_total > 0
        ? uploadInfo.ocr_pages_done / uploadInfo.ocr_pages_total
        : 0;
      overallPct = Math.round(50 + ocrPct * 45); // 50-95%
    } else if (uploadPhase === "complete") {
      overallPct = 98;
    }
  } else if (isDone) {
    overallPct = 100;
  }

  // Current message
  let message = t("uploadProgress.preparing");
  if (isUploading) {
    message = uploadInfo?.message || t("uploadProgress.processingFallback");
  } else if (isDone) {
    message = t("uploadProgress.extractionComplete");
  } else if (isError) {
    message = t("uploadProgress.processingFailed");
  }

  const totalPages = uploadInfo?.total_pages || 0;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("uploadProgress.ariaLabel")}
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0, 0, 0, 0.6)",
        zIndex: Z_MODAL,
      }}
    >
      <div
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 12,
          width: 480,
          maxWidth: "92%",
          boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border-color)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          {isDone ? (
            <CheckCircle2 size={18} color="#4caf50" style={{ flexShrink: 0 }} />
          ) : isError ? (
            <AlertCircle size={18} color="#f44336" style={{ flexShrink: 0 }} />
          ) : (
            <Loader2
              size={18}
              color="var(--accent-primary)"
              style={{ animation: "spin 1s linear infinite", flexShrink: 0 }}
            />
          )}
          <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
            {isDone ? t("uploadProgress.titleComplete") : isError ? t("uploadProgress.titleFailed") : t("uploadProgress.titleProcessing")}
          </span>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 20px" }}>
          {/* Document name + pipeline */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              marginBottom: 16,
            }}
          >
            <span
              style={{
                fontSize: 13,
                color: "var(--text-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                minWidth: 0,
              }}
            >
              {docName}
            </span>
          </div>

          {/* Phase steps indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 16 }}>
            {PHASE_LABEL_KEYS.map((p, i) => {
              const Icon = p.icon;
              const isActive = i === activePhaseIdx && !isDone && !isError;
              const isCompleted = isDone || i < activePhaseIdx;
              return (
                <div key={p.key} style={{ display: "flex", alignItems: "center", flex: 1 }}>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 4,
                      flex: 1,
                    }}
                  >
                    <div
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: isCompleted
                          ? "#4caf50"
                          : isActive
                            ? "var(--accent-primary)"
                            : "var(--bg-tertiary)",
                        transition: "background 0.3s ease",
                      }}
                    >
                      {isCompleted ? (
                        <CheckCircle2 size={14} color="#fff" />
                      ) : isActive ? (
                        <Icon size={14} color="#fff" />
                      ) : (
                        <Icon size={14} color="var(--text-muted)" />
                      )}
                    </div>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: isActive ? 600 : 400,
                        color: isCompleted
                          ? "#4caf50"
                          : isActive
                            ? "var(--accent-primary)"
                            : "var(--text-muted)",
                      }}
                    >
                      {t(p.labelKey)}
                    </span>
                  </div>
                  {i < PHASE_LABEL_KEYS.length - 1 && (
                    <div
                      style={{
                        height: 2,
                        flex: "0 0 20px",
                        background: i < activePhaseIdx || isDone ? "#4caf50" : "var(--bg-tertiary)",
                        transition: "background 0.3s ease",
                        marginBottom: 18,
                      }}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* Progress text */}
          <div
            style={{
              marginBottom: 6,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
            }}
          >
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{message}</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
              {overallPct}%
            </span>
          </div>

          {/* Progress bar */}
          <div
            style={{
              width: "100%",
              height: 8,
              background: "var(--bg-tertiary)",
              borderRadius: 4,
              overflow: "hidden",
              marginBottom: 16,
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${overallPct}%`,
                background: isError
                  ? "#f44336"
                  : isDone
                    ? "#4caf50"
                    : "var(--accent-primary)",
                borderRadius: 4,
                transition: "width 0.3s ease",
              }}
            />
          </div>

          {/* Extraction/OCR page progress (during upload) */}
          {isUploading && totalPages > 0 && (
            <div
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                marginBottom: 16,
                padding: "8px 12px",
                border: "1px solid var(--border-color)",
                borderRadius: 6,
              }}
            >
              {uploadPhase === "extracting" && (
                <div>
                  {t("uploadProgress.extractingPage", { current: uploadInfo?.current_page ?? 0, total: totalPages })}
                </div>
              )}
              {uploadPhase === "ocr" && (
                <>
                  <div>{t("uploadProgress.ocrPage", { current: uploadInfo?.ocr_pages_done ?? 0, total: uploadInfo?.ocr_pages_total ?? 0 })}</div>
                  <div
                    style={{
                      height: 4,
                      background: "var(--bg-tertiary)",
                      borderRadius: 2,
                      overflow: "hidden",
                      marginTop: 6,
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width:
                          uploadInfo && uploadInfo.ocr_pages_total > 0
                            ? `${Math.round(
                                (uploadInfo.ocr_pages_done / uploadInfo.ocr_pages_total) * 100,
                              )}%`
                            : "0%",
                        background: "linear-gradient(90deg, #5b9bd5, #7ec8e3)",
                        borderRadius: 2,
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </>
              )}
            </div>
          )}

          {/* Footer stats */}
          <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Clock size={12} />
              <span>{formatElapsed(elapsed)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
