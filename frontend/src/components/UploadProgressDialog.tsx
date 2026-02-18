/**
 * UploadProgressDialog — unified progress dialog for document upload pipeline.
 *
 * Shows three sequential phases:
 *   1. Extraction (page rendering via PDFium)
 *   2. OCR (Tesseract per-page, if needed)
 *   3. Detection (PII entity analysis per-page)
 *
 * Polls both getUploadProgress and getDetectionProgress from the backend.
 */

import { useEffect, useState, useRef, useMemo } from "react";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  FileText,
  Clock,
  Shield,
  ScanSearch,
  Eye,
} from "lucide-react";
import { getUploadProgress, getDetectionProgress } from "../api";
import type { UploadProgressInfo } from "../api";
import type { DetectionProgressData } from "../types";
import { Z_MODAL } from "../zIndex";
import { useDetectionStore } from "../store";

interface Props {
  /** Upload progress tracking ID (passed to uploadDocument). */
  uploadProgressId: string | null;
  /** Document ID (available after upload completes, used for detection polling). */
  docId: string | null;
  /** Document name for display. */
  docName: string;
  /** Current pipeline phase from the hook. */
  phase: "uploading" | "detecting" | "done" | "error";
  /** Whether visible. */
  visible: boolean;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

/** Phase config for the three-step indicator. */
const PHASES = [
  { key: "extracting", label: "Extract", icon: FileText },
  { key: "ocr", label: "OCR", icon: ScanSearch },
  { key: "detecting", label: "Detect", icon: Eye },
] as const;

export default function UploadProgressDialog({
  uploadProgressId,
  docId,
  docName,
  phase,
  visible,
}: Props) {
  const { detectionSettings } = useDetectionStore();
  const [uploadInfo, setUploadInfo] = useState<UploadProgressInfo | null>(null);
  const [detectionInfo, setDetectionInfo] = useState<DetectionProgressData | null>(null);
  const uploadPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const detectionPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  // Poll detection progress
  useEffect(() => {
    if (!visible || !docId || phase !== "detecting") {
      return;
    }
    const poll = async () => {
      try {
        const info = await getDetectionProgress(docId);
        setDetectionInfo(info);
      } catch {
        // ignore
      }
    };
    poll();
    detectionPollRef.current = setInterval(poll, 800);
    return () => {
      if (detectionPollRef.current) clearInterval(detectionPollRef.current);
    };
  }, [visible, docId, phase]);

  // Reset state when dialog opens for a new file
  useEffect(() => {
    if (visible) {
      setUploadInfo(null);
      setDetectionInfo(null);
    }
  }, [visible, uploadProgressId]);

  if (!visible) return null;

  // Determine which of the 3 phases is active
  const uploadPhase = uploadInfo?.phase ?? "starting";
  const isUploading = phase === "uploading";
  const isDetecting = phase === "detecting";
  const isDone = phase === "done";
  const isError = phase === "error";

  // Compute active phase index (0=extracting, 1=ocr, 2=detecting)
  let activePhaseIdx = 0;
  if (isUploading) {
    if (uploadPhase === "ocr") activePhaseIdx = 1;
    else if (uploadPhase === "extracting") activePhaseIdx = 0;
    else if (uploadPhase === "complete") activePhaseIdx = 2; // Upload done, about to detect
    else activePhaseIdx = 0;
  } else if (isDetecting || isDone) {
    activePhaseIdx = 2;
  }

  // Overall percentage (0-100 across all 3 phases: each gets ~33%)
  let overallPct = 0;
  if (isUploading) {
    if (uploadPhase === "starting") {
      overallPct = 2;
    } else if (uploadPhase === "extracting") {
      const pagePct = uploadInfo && uploadInfo.total_pages > 0
        ? uploadInfo.current_page / uploadInfo.total_pages
        : 0;
      overallPct = Math.round(2 + pagePct * 28); // 2-30%
    } else if (uploadPhase === "ocr") {
      const ocrPct = uploadInfo && uploadInfo.ocr_pages_total > 0
        ? uploadInfo.ocr_pages_done / uploadInfo.ocr_pages_total
        : 0;
      overallPct = Math.round(30 + ocrPct * 30); // 30-60%
    } else if (uploadPhase === "complete") {
      overallPct = 60;
    }
  } else if (isDetecting) {
    const detPct = detectionInfo && detectionInfo.total_pages > 0
      ? detectionInfo.pages_done / detectionInfo.total_pages
      : 0;
    overallPct = Math.round(60 + detPct * 38); // 60-98%
  } else if (isDone) {
    overallPct = 100;
  }

  // Current message
  let message = "Preparing…";
  if (isUploading) {
    message = uploadInfo?.message || "Processing document…";
  } else if (isDetecting) {
    const dp = detectionInfo;
    if (dp && dp.total_pages > 0) {
      message = `Analyzing page ${dp.current_page} of ${dp.total_pages}`;
    } else {
      message = "Analyzing document for PII entities…";
    }
  } else if (isDone) {
    message = "Processing complete";
  } else if (isError) {
    message = "Processing failed";
  }

  const regionsFound = detectionInfo?.regions_found ?? 0;
  const detPageStatuses = detectionInfo?.page_statuses ?? [];
  const totalPages = uploadInfo?.total_pages || detectionInfo?.total_pages || 0;

  // Build active pipeline label
  const pipelineSteps: string[] = [];
  if (detectionSettings.regex_enabled) pipelineSteps.push("Regex");
  if (detectionSettings.ner_enabled) pipelineSteps.push("NER");
  if (detectionSettings.llm_detection_enabled) pipelineSteps.push("LLM");
  const pipelineLabel = pipelineSteps.join(" → ");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Upload progress"
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
            {isDone ? "Processing Complete" : isError ? "Processing Failed" : "Processing Document"}
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
            {(isDetecting || isDone) && pipelineLabel && (
              <span
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}
              >
                {pipelineLabel}
              </span>
            )}
          </div>

          {/* Phase steps indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 16 }}>
            {PHASES.map((p, i) => {
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
                      {p.label}
                    </span>
                  </div>
                  {i < PHASES.length - 1 && (
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

          {/* Per-page status list (during detection) */}
          {isDetecting && detPageStatuses.length > 0 && (
            <div
              style={{
                maxHeight: 150,
                overflowY: "auto",
                border: "1px solid var(--border-color)",
                borderRadius: 6,
                marginBottom: 16,
              }}
            >
              {detPageStatuses.map((ps) => (
                <div
                  key={ps.page}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "5px 12px",
                    borderBottom:
                      ps.page < detPageStatuses.length ? "1px solid var(--border-color)" : "none",
                    background: ps.status === "running" ? "rgba(33,150,243,0.06)" : "transparent",
                  }}
                >
                  <div style={{ width: 14, display: "flex", justifyContent: "center", flexShrink: 0 }}>
                    {ps.status === "done" ? (
                      <CheckCircle2 size={12} color="#4caf50" />
                    ) : ps.status === "running" ? (
                      <Loader2
                        size={12}
                        color="var(--accent-primary)"
                        style={{ animation: "spin 1s linear infinite" }}
                      />
                    ) : (
                      <div
                        style={{
                          width: 7,
                          height: 7,
                          borderRadius: "50%",
                          background: "var(--bg-tertiary)",
                          border: "1px solid var(--text-muted)",
                        }}
                      />
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      color:
                        ps.status === "done"
                          ? "var(--text-primary)"
                          : ps.status === "running"
                            ? "var(--accent-primary)"
                            : "var(--text-muted)",
                      fontWeight: ps.status === "running" ? 600 : 400,
                      flex: 1,
                    }}
                  >
                    Page {ps.page}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-secondary)", minWidth: 48, textAlign: "right" }}>
                    {ps.status === "done"
                      ? `${ps.regions} region${ps.regions !== 1 ? "s" : ""}`
                      : ps.status === "running"
                        ? "Analyzing…"
                        : "Pending"}
                  </span>
                </div>
              ))}
            </div>
          )}

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
                  Extracting page {uploadInfo?.current_page ?? 0} of {totalPages}
                </div>
              )}
              {uploadPhase === "ocr" && (
                <>
                  <div>OCR processing: {uploadInfo?.ocr_pages_done ?? 0} of {uploadInfo?.ocr_pages_total ?? 0} pages</div>
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
            {(isDetecting || isDone) && (
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <Shield size={12} />
                <span>
                  {regionsFound} region{regionsFound !== 1 ? "s" : ""} found
                </span>
              </div>
            )}
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
