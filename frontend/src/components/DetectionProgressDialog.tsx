/** Modal dialog showing real-time PII detection progress. */

import { useEffect, useState, useRef } from "react";
import { Loader2, CheckCircle2, AlertCircle, FileSearch, Clock, Shield } from "lucide-react";
import { getDetectionProgress } from "../api";
import { Z_MODAL } from "../zIndex";
import type { DetectionProgressData, DetectionProgressPageStatus } from "../types";

interface Props {
  docId: string;
  docName: string;
  /** Called by parent once docDetecting flips to false (detection call resolved). */
  visible: boolean;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export default function DetectionProgressDialog({ docId, docName, visible }: Props) {
  const [progress, setProgress] = useState<DetectionProgressData | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!visible || !docId) {
      setProgress(null);
      return;
    }

    // Poll every 500ms
    const poll = async () => {
      try {
        const data = await getDetectionProgress(docId);
        setProgress(data);
      } catch {
        // Ignore poll errors
      }
    };

    poll(); // immediate first poll
    intervalRef.current = setInterval(poll, 1500);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [visible, docId]);

  if (!visible) return null;

  const totalPages = progress?.total_pages || 0;
  const pagesDone = progress?.pages_done || 0;
  const pct = totalPages > 0 ? Math.round((pagesDone / totalPages) * 100) : 0;
  const isRunning = progress?.status === "running";
  const isComplete = progress?.status === "complete";
  const isError = progress?.status === "error";
  const elapsed = progress?.elapsed_seconds || 0;
  const regionsFound = progress?.regions_found || 0;
  const pageStatuses: DetectionProgressPageStatus[] = progress?.page_statuses || [];

  return (
    <div role="dialog" aria-modal="true" aria-label="Detection progress" style={{
      position: "absolute",
      inset: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "rgba(0, 0, 0, 0.6)",
      zIndex: Z_MODAL,
    }}>
      <div style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
        borderRadius: 12,
        width: 440,
        maxWidth: "92%",
        boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: "1px solid var(--border-color)",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          {isRunning ? (
            <Loader2 size={18} color="var(--accent-primary)" style={{ animation: "spin 1s linear infinite", flexShrink: 0 }} />
          ) : isComplete ? (
            <CheckCircle2 size={18} color="#4caf50" style={{ flexShrink: 0 }} />
          ) : isError ? (
            <AlertCircle size={18} color="#f44336" style={{ flexShrink: 0 }} />
          ) : (
            <FileSearch size={18} color="var(--text-secondary)" style={{ flexShrink: 0 }} />
          )}
          <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
            {isComplete ? "Detection Complete" : isError ? "Detection Failed" : "Detecting PII Entities"}
          </span>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 20px" }}>
          {/* Document name */}
          <div style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            marginBottom: 16,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {docName}
          </div>

          {/* Overall progress */}
          <div style={{ marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {isComplete
                ? `All ${totalPages} pages processed`
                : totalPages > 0
                  ? `Processing page ${progress?.current_page || 0} of ${totalPages}`
                  : "Preparing…"}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
              {pct}%
            </span>
          </div>

          {/* Progress bar */}
          <div style={{
            width: "100%",
            height: 8,
            background: "var(--bg-tertiary)",
            borderRadius: 4,
            overflow: "hidden",
            marginBottom: 16,
          }}>
            <div style={{
              height: "100%",
              width: `${pct}%`,
              background: isError ? "#f44336" : isComplete ? "#4caf50" : "var(--accent-primary)",
              borderRadius: 4,
              transition: "width 0.3s ease",
            }} />
          </div>

          {/* Per-page progress list */}
          {pageStatuses.length > 0 && (
            <div style={{
              maxHeight: 180,
              overflowY: "auto",
              border: "1px solid var(--border-color)",
              borderRadius: 6,
              marginBottom: 16,
            }}>
              {pageStatuses.map((ps) => (
                <div key={ps.page} style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 12px",
                  borderBottom: ps.page < pageStatuses.length ? "1px solid var(--border-color)" : "none",
                  background: ps.status === "running" ? "rgba(33,150,243,0.06)" : "transparent",
                }}>
                  {/* Status icon */}
                  <div style={{ width: 16, display: "flex", justifyContent: "center", flexShrink: 0 }}>
                    {ps.status === "done" ? (
                      <CheckCircle2 size={13} color="#4caf50" />
                    ) : ps.status === "running" ? (
                      <Loader2 size={13} color="var(--accent-primary)" style={{ animation: "spin 1s linear infinite" }} />
                    ) : (
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--bg-tertiary)", border: "1px solid var(--text-muted)" }} />
                    )}
                  </div>

                  {/* Page label */}
                  <span style={{
                    fontSize: 12,
                    color: ps.status === "done" ? "var(--text-primary)" : ps.status === "running" ? "var(--accent-primary)" : "var(--text-muted)",
                    fontWeight: ps.status === "running" ? 600 : 400,
                    flex: 1,
                  }}>
                    Page {ps.page}
                  </span>

                  {/* Region count or status */}
                  <span style={{ fontSize: 11, color: "var(--text-secondary)", minWidth: 50, textAlign: "right" }}>
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

          {/* Footer stats */}
          <div style={{
            display: "flex",
            gap: 16,
            fontSize: 12,
            color: "var(--text-secondary)",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Shield size={12} />
              <span>{regionsFound} region{regionsFound !== 1 ? "s" : ""} found</span>
            </div>
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
