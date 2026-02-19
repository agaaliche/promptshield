/**
 * DetectionProgressDialog — shows per-pipeline-step progress
 * while PII detection (initial or re-detection) is running.
 *
 * Polls GET /api/documents/{id}/detection-progress every 800ms.
 * Displays pipeline steps (Regex → NER → GLiNER → LLM → Merge)
 * with per-page status and live region count.
 */

import { useEffect, useState, useRef } from "react";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Shield,
  Clock,
  FileText,
} from "lucide-react";
import { getDetectionProgress } from "../api";
import type { DetectionProgressData, DetectionProgressPageStatus } from "../types";
import { Z_MODAL } from "../zIndex";

interface Props {
  docId: string;
  docName: string;
  visible: boolean;
}

/* Human-readable labels for pipeline step keys */
const STEP_LABELS: Record<string, string> = {
  regex: "Regex",
  ner: "NER",
  gliner: "GLiNER",
  llm: "LLM",
  merge: "Merge",
};

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

/**
 * Determine the "furthest" pipeline step across all running pages
 * so we can show which pipeline phase the detection is currently in.
 */
function currentGlobalStep(data: DetectionProgressData): string | null {
  const steps = data.pipeline_steps ?? [];
  if (steps.length === 0) return null;
  let maxIdx = -1;
  for (const ps of data.page_statuses) {
    if (ps.status === "running" && ps.pipeline_step) {
      const idx = steps.indexOf(ps.pipeline_step);
      if (idx > maxIdx) maxIdx = idx;
    }
  }
  return maxIdx >= 0 ? steps[maxIdx] : null;
}

export default function DetectionProgressDialog({ docId, docName, visible }: Props) {
  const [progress, setProgress] = useState<DetectionProgressData | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);

  // Local elapsed timer
  useEffect(() => {
    if (!visible) return;
    startRef.current = Date.now();
    const t = setInterval(() => setElapsed((Date.now() - startRef.current) / 1000), 500);
    return () => clearInterval(t);
  }, [visible]);

  // Poll detection progress
  useEffect(() => {
    if (!visible || !docId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getDetectionProgress(docId);
        if (!cancelled) setProgress(data);
      } catch {
        // ignore transient errors
      }
    };
    poll();
    pollRef.current = setInterval(poll, 800);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [visible, docId]);

  // Reset on open
  useEffect(() => {
    if (visible) setProgress(null);
  }, [visible, docId]);

  if (!visible) return null;

  const status = progress?.status ?? "running";
  const isRunning = status === "running";
  const isDone = status === "complete";
  const isError = status === "error";

  const totalPages = progress?.total_pages ?? 0;
  const pagesDone = progress?.pages_done ?? 0;
  const regionsFound = progress?.regions_found ?? 0;
  const pipelineSteps = progress?.pipeline_steps ?? [];
  const globalStep = progress ? currentGlobalStep(progress) : null;
  const pageStatuses: DetectionProgressPageStatus[] = progress?.page_statuses ?? [];

  // Overall percentage based on pages done
  let overallPct = 0;
  if (totalPages > 0) {
    overallPct = Math.round((pagesDone / totalPages) * 100);
  }
  if (isDone) overallPct = 100;

  // Status message
  let message = "Starting detection…";
  if (isRunning && globalStep) {
    message = `Running ${STEP_LABELS[globalStep] ?? globalStep} — page ${Math.min(pagesDone + 1, totalPages)} of ${totalPages}`;
  } else if (isRunning && totalPages > 0) {
    message = `Detecting — page ${Math.min(pagesDone + 1, totalPages)} of ${totalPages}`;
  } else if (isDone) {
    message = `Detection complete — ${regionsFound} region${regionsFound !== 1 ? "s" : ""} found`;
  } else if (isError) {
    message = progress?.error ?? "Detection failed";
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Detection progress"
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
          width: 520,
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
            {isDone
              ? "Detection Complete"
              : isError
                ? "Detection Failed"
                : "Detecting PII"}
          </span>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 20px" }}>
          {/* Document name */}
          <div style={{ marginBottom: 16 }}>
            <span
              style={{
                fontSize: 13,
                color: "var(--text-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                display: "block",
              }}
            >
              {docName}
            </span>
          </div>

          {/* Pipeline step indicators */}
          {pipelineSteps.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 0, marginBottom: 16 }}>
              {pipelineSteps.map((step, i) => {
                const label = STEP_LABELS[step] ?? step;
                const globalIdx = globalStep ? pipelineSteps.indexOf(globalStep) : -1;
                const stepDone = isDone || (isRunning && globalIdx > i);
                const stepActive = isRunning && globalIdx === i;

                return (
                  <div key={step} style={{ display: "flex", alignItems: "center", flex: 1 }}>
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
                          background: stepDone
                            ? "#4caf50"
                            : stepActive
                              ? "var(--accent-primary)"
                              : "var(--bg-tertiary)",
                          transition: "background 0.3s ease",
                        }}
                      >
                        {stepDone ? (
                          <CheckCircle2 size={14} color="#fff" />
                        ) : stepActive ? (
                          <Loader2
                            size={14}
                            color="#fff"
                            style={{ animation: "spin 1s linear infinite" }}
                          />
                        ) : (
                          <Shield size={14} color="var(--text-muted)" />
                        )}
                      </div>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: stepActive ? 600 : 400,
                          color: stepDone
                            ? "#4caf50"
                            : stepActive
                              ? "var(--accent-primary)"
                              : "var(--text-muted)",
                        }}
                      >
                        {label}
                      </span>
                    </div>
                    {i < pipelineSteps.length - 1 && (
                      <div
                        style={{
                          height: 2,
                          flex: "0 0 16px",
                          background: stepDone ? "#4caf50" : "var(--bg-tertiary)",
                          transition: "background 0.3s ease",
                          marginBottom: 18,
                        }}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Progress text + percentage */}
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

          {/* Overall progress bar */}
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

          {/* Per-page status list (scrollable, max ~6 rows visible) */}
          {pageStatuses.length > 1 && (
            <div
              style={{
                maxHeight: 160,
                overflowY: "auto",
                border: "1px solid var(--border-color)",
                borderRadius: 6,
                marginBottom: 16,
                fontSize: 11,
              }}
            >
              {pageStatuses.map((ps) => (
                <div
                  key={ps.page}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 10px",
                    borderBottom: "1px solid var(--border-color)",
                    background:
                      ps.status === "running"
                        ? "rgba(var(--accent-primary-rgb, 90, 130, 230), 0.08)"
                        : "transparent",
                  }}
                >
                  {/* Page label */}
                  <span style={{ width: 50, color: "var(--text-muted)", flexShrink: 0 }}>
                    <FileText size={10} style={{ marginRight: 3, verticalAlign: "middle" }} />
                    Page {ps.page}
                  </span>
                  {/* Status */}
                  <span
                    style={{
                      flex: 1,
                      color:
                        ps.status === "done"
                          ? "#4caf50"
                          : ps.status === "running"
                            ? "var(--accent-primary)"
                            : "var(--text-muted)",
                      fontWeight: ps.status === "running" ? 600 : 400,
                    }}
                  >
                    {ps.status === "running" && ps.pipeline_step
                      ? STEP_LABELS[ps.pipeline_step] ?? ps.pipeline_step
                      : ps.status === "done"
                        ? `Done — ${ps.regions} region${ps.regions !== 1 ? "s" : ""}`
                        : "Pending"}
                  </span>
                  {/* Mini spinner or check */}
                  {ps.status === "running" && (
                    <Loader2
                      size={10}
                      color="var(--accent-primary)"
                      style={{ animation: "spin 1s linear infinite", flexShrink: 0 }}
                    />
                  )}
                  {ps.status === "done" && (
                    <CheckCircle2 size={10} color="#4caf50" style={{ flexShrink: 0 }} />
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Footer stats */}
          <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Clock size={12} />
              <span>{formatElapsed(progress?.elapsed_seconds ?? elapsed)}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Shield size={12} />
              <span>{regionsFound} region{regionsFound !== 1 ? "s" : ""}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <FileText size={12} />
              <span>
                {pagesDone}/{totalPages} page{totalPages !== 1 ? "s" : ""}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
