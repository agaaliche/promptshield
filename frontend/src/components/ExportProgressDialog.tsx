/**
 * ExportProgressDialog — unified export dialog that shows:
 *   1. Real-time export/anonymization progress (polling backend)
 *   2. On completion: success panel with file path, open/folder buttons,
 *      and optional PDF split for AI ingestion.
 */

import { useEffect, useState, useRef } from "react";
import {
  Loader2,
  CheckCircle2,
  AlertCircle,
  Download,
  Clock,
  FileText,
  FolderOpen,
  X,
  Copy,
  Check,
  Scissors,
  Package,
} from "lucide-react";
import { getExportProgress, shellOpenFile, shellRevealFile, splitExportFile, getSplitProgress } from "../api";
import type { ExportProgressInfo, ExportDocStatus, ExportSaveResult, SplitFileResult, SplitProgressInfo } from "../api";
import { Z_TOP_DIALOG } from "../zIndex";

interface Props {
  exportId: string | null;
  visible: boolean;
  /** Passed in once the export API call resolves. */
  exportResult: ExportSaveResult | null;
  onClose: () => void;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExportProgressDialog({
  exportId,
  visible,
  exportResult,
  onClose,
}: Props) {
  const [progress, setProgress] = useState<ExportProgressInfo | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);

  // ── Success / split state ──
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState("");
  const [maxSizeMb, setMaxSizeMb] = useState("30");
  const [isSplitting, setIsSplitting] = useState(false);
  const [splitResult, setSplitResult] = useState<SplitFileResult | null>(null);
  const [splitError, setSplitError] = useState("");
  const [splitProgressId, setSplitProgressId] = useState<string | null>(null);
  const [splitProgress, setSplitProgress] = useState<SplitProgressInfo | null>(null);
  const splitPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Reset success state when dialog opens
  useEffect(() => {
    if (visible) {
      setCopied(false);
      setActionError("");
      setMaxSizeMb("30");
      setIsSplitting(false);
      setSplitResult(null);
      setSplitError("");
      setSplitProgressId(null);
      setSplitProgress(null);
      if (splitPollRef.current) clearInterval(splitPollRef.current);
    }
  }, [visible]);

  // Local elapsed timer
  useEffect(() => {
    if (!visible) return;
    startTimeRef.current = Date.now();
    const t = setInterval(() => setElapsed((Date.now() - startTimeRef.current) / 1000), 500);
    return () => clearInterval(t);
  }, [visible]);

  // Poll export progress
  useEffect(() => {
    if (!visible || !exportId) {
      setProgress(null);
      return;
    }

    const poll = async () => {
      try {
        const data = await getExportProgress(exportId);
        setProgress(data);
      } catch {
        // Ignore poll errors
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 600);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [visible, exportId]);

  // Poll split progress
  useEffect(() => {
    if (!splitProgressId || !isSplitting) {
      if (splitPollRef.current) {
        clearInterval(splitPollRef.current);
        splitPollRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const data = await getSplitProgress(splitProgressId);
        setSplitProgress(data);
      } catch {
        // ignore poll errors
      }
    };

    poll();
    splitPollRef.current = setInterval(poll, 400);

    return () => {
      if (splitPollRef.current) clearInterval(splitPollRef.current);
    };
  }, [splitProgressId, isSplitting]);

  if (!visible) return null;

  // ── Progress calculations ──
  const docsTotal = progress?.docs_total || 0;
  const docsDone = progress?.docs_done || 0;
  const docsFailed = progress?.docs_failed || 0;
  const isComplete = !!exportResult;
  const isError = !exportResult && progress?.status === "error";
  const isSaving = progress?.phase === "saving";
  const message = progress?.message || "Preparing export…";
  const docStatuses: ExportDocStatus[] = progress?.doc_statuses || [];

  const pct =
    isComplete
      ? 100
      : isSaving
        ? 95
        : docsTotal > 0
          ? Math.round(((docsDone + docsFailed) / docsTotal) * 90)
          : 0;

  // ── Success panel helpers ──
  const savedPath = exportResult?.saved_path ?? "";
  const filename = exportResult?.filename ?? "";
  const fileCount = exportResult?.file_count ?? 0;
  const totalSize = exportResult?.total_size ?? 0;
  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const fileSizeMb = totalSize / (1024 * 1024);
  const showSplitOption = isPdf && fileSizeMb > 5;

  const displayPath = splitResult?.saved_path ?? savedPath;
  const displayFilename = splitResult?.filename ?? filename;

  const handleCopyPath = async () => {
    const pathToCopy = splitResult?.saved_path ?? savedPath;
    try {
      await navigator.clipboard.writeText(pathToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = pathToCopy;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleOpenFile = async () => {
    try {
      setActionError("");
      await shellOpenFile(savedPath);
    } catch (e: unknown) {
      setActionError(`Could not open file: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleRevealFile = async () => {
    try {
      setActionError("");
      await shellRevealFile(splitResult?.saved_path ?? savedPath);
    } catch (e: unknown) {
      setActionError(`Could not open folder: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleSplit = async () => {
    const mb = parseFloat(maxSizeMb);
    if (isNaN(mb) || mb <= 0) {
      setSplitError("Enter a valid size in MB");
      return;
    }
    const sid = `split_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setSplitProgressId(sid);
    setSplitProgress(null);
    setIsSplitting(true);
    setSplitError("");
    setSplitResult(null);
    try {
      const result = await splitExportFile(savedPath, mb, sid);
      setSplitResult(result);
    } catch (e: unknown) {
      setSplitError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsSplitting(false);
      setSplitProgressId(null);
    }
  };

  const handleOpenSplitResult = async () => {
    if (!splitResult) return;
    try {
      setActionError("");
      if (splitResult.split) {
        await shellRevealFile(splitResult.saved_path);
      } else {
        await shellOpenFile(splitResult.saved_path);
      }
    } catch (e: unknown) {
      setActionError(`Could not open: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Export progress"
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0, 0, 0, 0.6)",
        zIndex: Z_TOP_DIALOG,
      }}
      onClick={isComplete || isError ? onClose : undefined}
    >
      <div
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 12,
          width: 480,
          maxWidth: "92%",
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
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
          {isComplete ? (
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
          <span style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)", flex: 1 }}>
            {isComplete
              ? "Export Complete"
              : isError
                ? "Export Failed"
                : isSaving
                  ? "Saving to Downloads"
                  : "Exporting Documents"}
          </span>
          {(isComplete || isError) && (
            <button
              className="btn-ghost"
              onClick={onClose}
              style={{ padding: 4, lineHeight: 0 }}
              aria-label="Close"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {/* Body */}
        <div style={{ padding: "16px 20px", overflowY: "auto", flex: 1 }}>
          {/* ───── Progress view (while exporting) ───── */}
          {!isComplete && (
            <>
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
                  {pct}%
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
                    width: `${pct}%`,
                    background: isError ? "#f44336" : "var(--accent-primary)",
                    borderRadius: 4,
                    transition: "width 0.3s ease",
                  }}
                />
              </div>

              {/* Per-document status list */}
              {docStatuses.length > 0 && (
                <div
                  style={{
                    maxHeight: 200,
                    overflowY: "auto",
                    border: "1px solid var(--border-color)",
                    borderRadius: 6,
                    marginBottom: 16,
                  }}
                >
                  {docStatuses.map((ds, i) => (
                    <div
                      key={ds.doc_id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "6px 12px",
                        borderBottom:
                          i < docStatuses.length - 1
                            ? "1px solid var(--border-color)"
                            : "none",
                        background:
                          ds.status === "running" ? "rgba(33,150,243,0.06)" : "transparent",
                      }}
                    >
                      <div
                        style={{
                          width: 16,
                          display: "flex",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        {ds.status === "done" ? (
                          <CheckCircle2 size={13} color="#4caf50" />
                        ) : ds.status === "running" ? (
                          <Loader2
                            size={13}
                            color="var(--accent-primary)"
                            style={{ animation: "spin 1s linear infinite" }}
                          />
                        ) : ds.status === "error" ? (
                          <AlertCircle size={13} color="#f44336" />
                        ) : (
                          <div
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: "var(--bg-tertiary)",
                              border: "1px solid var(--text-muted)",
                            }}
                          />
                        )}
                      </div>

                      <FileText
                        size={11}
                        style={{ color: "var(--text-muted)", flexShrink: 0 }}
                      />
                      <span
                        style={{
                          fontSize: 12,
                          color:
                            ds.status === "done"
                              ? "var(--text-primary)"
                              : ds.status === "running"
                                ? "var(--accent-primary)"
                                : ds.status === "error"
                                  ? "#f44336"
                                  : "var(--text-muted)",
                          fontWeight: ds.status === "running" ? 600 : 400,
                          flex: 1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {ds.name}
                      </span>

                      <span
                        style={{
                          fontSize: 10,
                          color: "var(--text-secondary)",
                          flexShrink: 0,
                        }}
                      >
                        {ds.status === "done"
                          ? "Done"
                          : ds.status === "running"
                            ? "Anonymizing…"
                            : ds.status === "error"
                              ? "Failed"
                              : "Pending"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Footer stats */}
              <div
                style={{
                  display: "flex",
                  gap: 16,
                  fontSize: 12,
                  color: "var(--text-secondary)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <Download size={12} />
                  <span>
                    {docsDone}/{docsTotal} file{docsTotal !== 1 ? "s" : ""}
                    {docsFailed > 0 ? ` (${docsFailed} failed)` : ""}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <Clock size={12} />
                  <span>{formatElapsed(elapsed)}</span>
                </div>
              </div>
            </>
          )}

          {/* ───── Success view (export complete) ───── */}
          {isComplete && (
            <>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                {splitResult
                  ? `${splitResult.part_count} part${splitResult.part_count !== 1 ? "s" : ""} (${formatBytes(splitResult.total_size)})`
                  : `${fileCount} file${fileCount !== 1 ? "s" : ""} exported (${formatBytes(totalSize)}) in ${formatElapsed(elapsed)}`}
              </div>

              {/* File path display */}
              <div
                style={{
                  background: "rgba(0,0,0,0.2)",
                  border: "1px solid var(--border-color)",
                  borderRadius: 6,
                  padding: "10px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 12,
                }}
              >
                <FileText size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: "var(--text-primary)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {displayFilename}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      marginTop: 2,
                    }}
                    title={displayPath}
                  >
                    {displayPath}
                  </div>
                </div>
                <button
                  className="btn-ghost"
                  onClick={handleCopyPath}
                  style={{ padding: 4, lineHeight: 0, flexShrink: 0 }}
                  title="Copy path"
                >
                  {copied ? (
                    <Check size={14} style={{ color: "#4caf50" }} />
                  ) : (
                    <Copy size={14} />
                  )}
                </button>
              </div>

              {/* Split result — part list */}
              {splitResult?.split && splitResult.parts && (
                <div
                  style={{
                    background: "rgba(76,175,80,0.08)",
                    border: "1px solid rgba(76,175,80,0.25)",
                    borderRadius: 6,
                    padding: "10px 12px",
                    marginBottom: 12,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      marginBottom: 6,
                    }}
                  >
                    <Package size={13} style={{ color: "#4caf50" }} />
                    <span style={{ fontSize: 12, fontWeight: 500, color: "#4caf50" }}>
                      Split into {splitResult.part_count} parts
                    </span>
                  </div>
                  <div style={{ maxHeight: 120, overflowY: "auto" }}>
                    {splitResult.parts.map((name, i) => (
                      <div
                        key={i}
                        style={{
                          fontSize: 11,
                          color: "var(--text-secondary)",
                          padding: "2px 0",
                          fontFamily: "monospace",
                        }}
                      >
                        {name}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Split result — no split needed */}
              {splitResult && !splitResult.split && (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-secondary)",
                    marginBottom: 12,
                    padding: "8px 10px",
                    background: "rgba(255,193,7,0.08)",
                    border: "1px solid rgba(255,193,7,0.25)",
                    borderRadius: 6,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <AlertCircle size={13} style={{ color: "#ffc107" }} />
                  {splitResult.message}
                </div>
              )}

              {/* Split option for large PDFs */}
              {showSplitOption && !splitResult?.split && (
                <div
                  style={{
                    background: "rgba(0,0,0,0.15)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 6,
                    padding: "10px 12px",
                    marginBottom: 12,
                  }}
                >
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      marginBottom: 8,
                    }}
                  >
                    <Scissors
                      size={12}
                      style={{ verticalAlign: "middle", marginRight: 4 }}
                    />
                    Split file for AI ingestion (parts are named sequentially)
                  </div>

                  {/* Controls row */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <label
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Max size
                    </label>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={maxSizeMb}
                      onChange={(e) => setMaxSizeMb(e.target.value)}
                      disabled={isSplitting}
                      style={{
                        width: 70,
                        padding: "4px 8px",
                        fontSize: 12,
                        borderRadius: 4,
                        border: "1px solid var(--border-color)",
                        background: "var(--bg-primary)",
                        color: "var(--text-primary)",
                        textAlign: "right",
                      }}
                    />
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>MB</span>
                    <button
                      className="btn-primary btn-sm"
                      onClick={handleSplit}
                      disabled={isSplitting}
                      style={{
                        marginLeft: "auto",
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        minWidth: 80,
                        justifyContent: "center",
                      }}
                    >
                      {isSplitting ? (
                        <>
                          <Loader2
                            size={13}
                            style={{ animation: "spin 1s linear infinite" }}
                          />
                          Splitting…
                        </>
                      ) : (
                        <>
                          <Scissors size={13} />
                          Split
                        </>
                      )}
                    </button>
                  </div>

                  {/* Split progress bar */}
                  {isSplitting && splitProgress && splitProgress.phase !== "idle" && (() => {
                    const sp = splitProgress;
                    let splitPct = 0;
                    if (sp.phase === "sampling" && sp.total_pages) {
                      // Sampling is 0-50%
                      splitPct = Math.round(((sp.pages_sampled || 0) / sp.total_pages) * 50);
                    } else if (sp.phase === "writing" && sp.total_parts) {
                      // Writing is 50-100%
                      splitPct = 50 + Math.round(((sp.parts_done || 0) / sp.total_parts) * 50);
                    } else if (sp.phase === "done") {
                      splitPct = 100;
                    }
                    return (
                      <div style={{ marginTop: 10 }}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "baseline",
                            marginBottom: 4,
                          }}
                        >
                          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                            {sp.message || "Splitting…"}
                          </span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>
                            {splitPct}%
                          </span>
                        </div>
                        <div
                          style={{
                            width: "100%",
                            height: 6,
                            background: "var(--bg-tertiary)",
                            borderRadius: 3,
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              height: "100%",
                              width: `${splitPct}%`,
                              background: "var(--accent-primary)",
                              borderRadius: 3,
                              transition: "width 0.3s ease",
                            }}
                          />
                        </div>
                      </div>
                    );
                  })()}

                  {splitError && (
                    <div style={{ fontSize: 11, color: "#f44336", marginTop: 6 }}>
                      {splitError}
                    </div>
                  )}
                </div>
              )}

              {actionError && (
                <div style={{ fontSize: 11, color: "#f44336", marginBottom: 8 }}>
                  {actionError}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer — only shown when complete or error */}
        {(isComplete || isError) && (
          <div
            style={{
              padding: "12px 16px",
              borderTop: "1px solid var(--border-color)",
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              gap: 8,
              background: "rgba(0,0,0,0.15)",
              borderRadius: "0 0 12px 12px",
            }}
          >
            <button className="btn-ghost btn-sm" onClick={onClose}>
              Close
            </button>
            {isComplete && (
              <>
                <button
                  className="btn-ghost btn-sm"
                  onClick={handleRevealFile}
                  style={{ display: "flex", alignItems: "center", gap: 5 }}
                >
                  <FolderOpen size={14} />
                  Open Folder
                </button>
                {splitResult?.split ? (
                  <button
                    className="btn-primary btn-sm"
                    onClick={handleOpenSplitResult}
                    style={{ display: "flex", alignItems: "center", gap: 5 }}
                  >
                    <Package size={14} />
                    Open Split Zip
                  </button>
                ) : (
                  <button
                    className="btn-primary btn-sm"
                    onClick={handleOpenFile}
                    style={{ display: "flex", alignItems: "center", gap: 5 }}
                  >
                    <FileText size={14} />
                    Open File
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
