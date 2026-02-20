/**
 * ExportSuccessDialog — shown after a successful export.
 * Displays the saved file path with buttons to open the file
 * or reveal it in the OS file manager, and optionally split
 * large PDFs into smaller parts for AI ingestion.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  CheckCircle,
  FileText,
  FolderOpen,
  X,
  Copy,
  Check,
  Scissors,
  Loader2,
  Package,
  AlertCircle,
} from "../icons";
import { shellOpenFile, shellRevealFile, splitExportFile } from "../api";
import type { SplitFileResult } from "../api";
import { Z_TOP_DIALOG } from "../zIndex";

interface Props {
  open: boolean;
  onClose: () => void;
  savedPath: string;
  filename: string;
  fileCount: number;
  totalSize: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExportSuccessDialog({
  open,
  onClose,
  savedPath,
  filename,
  fileCount,
  totalSize,
}: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState("");

  // ── Split state ──
  const [maxSizeMb, setMaxSizeMb] = useState("30");
  const [isSplitting, setIsSplitting] = useState(false);
  const [splitResult, setSplitResult] = useState<SplitFileResult | null>(null);
  const [splitError, setSplitError] = useState("");

  if (!open) return null;

  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const fileSizeMb = totalSize / (1024 * 1024);
  // Show split option for PDFs larger than 5 MB
  const showSplitOption = isPdf && fileSizeMb > 5;

  const handleCopyPath = async () => {
    const pathToCopy = splitResult?.saved_path ?? savedPath;
    try {
      await navigator.clipboard.writeText(pathToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
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
      setActionError(t("exportSuccess.couldNotOpenFile", { error: e instanceof Error ? e.message : String(e) }));
    }
  };

  const handleRevealFile = async () => {
    try {
      setActionError("");
      await shellRevealFile(splitResult?.saved_path ?? savedPath);
    } catch (e: unknown) {
      setActionError(t("exportSuccess.couldNotOpenFolder", { error: e instanceof Error ? e.message : String(e) }));
    }
  };

  const handleSplit = async () => {
    const mb = parseFloat(maxSizeMb);
    if (isNaN(mb) || mb <= 0) {
      setSplitError(t("exportSuccess.enterValidSize"));
      return;
    }
    setIsSplitting(true);
    setSplitError("");
    setSplitResult(null);
    try {
      const result = await splitExportFile(savedPath, mb);
      setSplitResult(result);
    } catch (e: unknown) {
      setSplitError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsSplitting(false);
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
      setActionError(t("exportSuccess.couldNotOpen", { error: e instanceof Error ? e.message : String(e) }));
    }
  };

  // Which path/filename to show — switch to split result once available
  const displayPath = splitResult?.saved_path ?? savedPath;
  const displayFilename = splitResult?.filename ?? filename;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-success-title"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: Z_TOP_DIALOG,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-color)",
          borderRadius: 10,
          width: 460,
          maxWidth: "90vw",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 12px 40px rgba(0,0,0,0.4)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 16px 12px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <CheckCircle size={20} style={{ color: "#4caf50", flexShrink: 0 }} />
          <h2
            id="export-success-title"
            style={{ flex: 1, margin: 0, fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}
          >
            {t("exportSuccess.title")}
          </h2>
          <button
            className="btn-ghost"
            onClick={onClose}
            style={{ padding: 4, lineHeight: 0 }}
            aria-label={t("common.close")}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "16px" }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            {splitResult
              ? t("exportSuccess.nParts", { count: splitResult.part_count, size: formatBytes(splitResult.total_size) })
              : t("exportSuccess.nFilesExported", { count: fileCount, size: formatBytes(totalSize) })}
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
              title={t("exportSuccess.copyPath")}
            >
              {copied ? <Check size={14} style={{ color: "#4caf50" }} /> : <Copy size={14} />}
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
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <Package size={13} style={{ color: "#4caf50" }} />
                <span style={{ fontSize: 12, fontWeight: 500, color: "#4caf50" }}>
                  {t("exportSuccess.splitIntoParts", { count: splitResult.part_count })}
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
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
                <Scissors size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
                {t("exportSuccess.splitHint")}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <label style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                  {t("exportSuccess.maxSize")}
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
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{t("exportSuccess.mb")}</span>
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
                      <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
                      {t("exportSuccess.splitting")}
                    </>
                  ) : (
                    <>
                      <Scissors size={13} />
                      {t("exportSuccess.split")}
                    </>
                  )}
                </button>
              </div>
              {splitError && (
                <div style={{ fontSize: 11, color: "#f44336", marginTop: 6 }}>{splitError}</div>
              )}
            </div>
          )}

          {actionError && (
            <div style={{ fontSize: 11, color: "#f44336", marginBottom: 8 }}>{actionError}</div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 16px",
            borderTop: "1px solid var(--border-color)",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 8,
            background: "rgba(0,0,0,0.15)",
            borderRadius: "0 0 10px 10px",
          }}
        >
          <button className="btn-ghost btn-sm" onClick={onClose}>
            {t("common.close")}
          </button>
          <button
            className="btn-ghost btn-sm"
            onClick={handleRevealFile}
            style={{ display: "flex", alignItems: "center", gap: 5 }}
          >
            <FolderOpen size={14} />
            {t("exportSuccess.openFolder")}
          </button>
          {splitResult?.split ? (
            <button
              className="btn-primary btn-sm"
              onClick={handleOpenSplitResult}
              style={{ display: "flex", alignItems: "center", gap: 5 }}
            >
              <Package size={14} />
              {t("exportSuccess.openSplitZip")}
            </button>
          ) : (
            <button
              className="btn-primary btn-sm"
              onClick={handleOpenFile}
              style={{ display: "flex", alignItems: "center", gap: 5 }}
            >
              <FileText size={14} />
              {t("exportSuccess.openFile")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
