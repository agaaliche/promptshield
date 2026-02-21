/** De-tokenization view — paste text OR upload a file to replace tokens with originals. */

import { useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowRightLeft,
  Copy,
  AlertTriangle,
  CheckCircle2,
  Upload,
  FileText,
  Download,
  X,
} from "../icons";
import { detokenize, detokenizeFile, type DetokenizeFileResult } from "../api";
import { toErrorMessage } from "../errorUtils";
import { useUIStore } from "../store";

type Mode = "text" | "file";

const ACCEPTED_EXTENSIONS = ".txt,.csv,.pdf,.docx,.xlsx";

export default function DetokenizeView() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("text");

  // Text mode state
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [tokensReplaced, setTokensReplaced] = useState(0);
  const [unresolved, setUnresolved] = useState<string[]>([]);
  const [error, setError] = useState("");

  // File mode state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileResult, setFileResult] = useState<DetokenizeFileResult | null>(
    null,
  );
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { isProcessing, setIsProcessing } = useUIStore();

  // ── Text de-tokenization ──────────────────────────────────────────
  const handleDetokenizeText = useCallback(async () => {
    if (!input.trim()) return;
    setError("");
    setIsProcessing(true);
    try {
      const result = await detokenize(input);
      setOutput(result.original_text);
      setTokensReplaced(result.tokens_replaced);
      setUnresolved(result.unresolved_tokens);
    } catch (e: unknown) {
      setError(toErrorMessage(e) || "De-tokenization failed");
    } finally {
      setIsProcessing(false);
    }
  }, [input, setIsProcessing]);

  const copyOutput = useCallback(() => {
    navigator.clipboard.writeText(output);
  }, [output]);

  // ── File de-tokenization ──────────────────────────────────────────
  const handleFilePick = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;
    setSelectedFile(files[0]);
    setFileResult(null);
    setError("");
    setTokensReplaced(0);
    setUnresolved([]);
  }, []);

  const handleDetokenizeFile = useCallback(async () => {
    if (!selectedFile) return;
    setError("");
    setFileResult(null);
    setIsProcessing(true);
    try {
      const result = await detokenizeFile(selectedFile);
      setFileResult(result);
      setTokensReplaced(result.tokensReplaced);
      setUnresolved(result.unresolvedTokens);
    } catch (e: unknown) {
      setError(toErrorMessage(e) || "File de-tokenization failed");
    } finally {
      setIsProcessing(false);
    }
  }, [selectedFile, setIsProcessing]);

  const handleDownload = useCallback(() => {
    if (!fileResult) return;
    const url = URL.createObjectURL(fileResult.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileResult.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [fileResult]);

  const clearFile = useCallback(() => {
    setSelectedFile(null);
    setFileResult(null);
    setError("");
    setTokensReplaced(0);
    setUnresolved([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  // ── Drag & drop helpers ───────────────────────────────────────────
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);
  const onDragLeave = useCallback(() => setDragOver(false), []);
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleFilePick(e.dataTransfer.files);
    },
    [handleFilePick],
  );

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div style={S.container}>
      <h2 style={S.title}>{t("detokenize.title")}</h2>
      <p style={S.subtitle}>
        {t("detokenize.description")}
      </p>

      {/* Mode tabs */}
      <div style={S.tabs}>
        <button
          className={mode === "text" ? "btn-primary" : "btn-ghost"}
          style={S.tab}
          onClick={() => setMode("text")}
        >
          <FileText size={14} /> {t("detokenize.tabPasteText")}
        </button>
        <button
          className={mode === "file" ? "btn-primary" : "btn-ghost"}
          style={S.tab}
          onClick={() => setMode("file")}
        >
          <Upload size={14} /> {t("detokenize.tabUploadFile")}
        </button>
      </div>

      {/* ─── TEXT MODE ─── */}
      {mode === "text" && (
        <div style={S.columns}>
          <div style={S.column}>
            <label style={S.label}>{t("detokenize.inputLabel")}</label>
            <textarea
              style={S.textarea}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={t("detokenize.inputPlaceholder")}
              rows={18}
            />
          </div>

          <div style={S.center}>
            <button
              className="btn-primary"
              onClick={handleDetokenizeText}
              disabled={isProcessing || !input.trim()}
              title={t("detokenize.swapTokens")}
              style={{
                width: 52,
                height: 52,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 0,
                flexShrink: 0,
                zIndex: 2,
                boxShadow: "0 2px 12px rgba(0,0,0,0.4)",
                marginLeft: -28,
                marginRight: -28,
                opacity: 1,
              }}
            >
              <ArrowRightLeft size={22} />
            </button>
          </div>

          <div style={S.column}>
            <div style={S.outputHeader}>
              <label style={S.label}>{t("detokenize.outputLabel")}</label>
              {output && (
                <button className="btn-ghost btn-sm" onClick={copyOutput}>
                  <Copy size={12} /> {t("common.copy")}
                </button>
              )}
            </div>
            <textarea
              style={S.textarea}
              value={output}
              readOnly
              placeholder={t("detokenize.outputPlaceholder")}
              rows={18}
            />
          </div>
        </div>
      )}

      {/* ─── FILE MODE ─── */}
      {mode === "file" && (
        <div style={S.fileSection}>
          {/* Drop zone */}
          {!selectedFile && (
            <div
              style={{
                ...S.dropZone,
                ...(dragOver ? S.dropZoneActive : {}),
              }}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload
                size={40}
                style={{ color: "var(--text-tertiary)" }}
              />
              <p style={{ margin: 0, fontWeight: 600 }}>
                {t("detokenize.dropFileHint")}
              </p>
              <p
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: "var(--text-tertiary)",
                }}
              >
                {t("detokenize.supportedFiles")}
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS}
                style={{ display: "none" }}
                onChange={(e) => handleFilePick(e.target.files)}
              />
            </div>
          )}

          {/* Selected file */}
          {selectedFile && (
            <div style={S.fileCard}>
              <div style={S.fileInfo}>
                <FileText
                  size={24}
                  style={{ color: "var(--accent-primary)" }}
                />
                <div>
                  <div style={{ fontWeight: 600 }}>{selectedFile.name}</div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-tertiary)",
                    }}
                  >
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </div>
                </div>
                <button
                  className="btn-ghost btn-sm"
                  onClick={clearFile}
                  style={{ marginLeft: "auto" }}
                >
                  <X size={14} />
                </button>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button
                  className="btn-primary"
                  onClick={handleDetokenizeFile}
                  disabled={isProcessing}
                  style={{ padding: "10px 20px" }}
                >
                  <ArrowRightLeft size={16} />
                  {isProcessing ? t("detokenize.processingFile") : t("detokenize.swapTokens")}
                </button>

                {fileResult && (
                  <button
                    className="btn-primary"
                    onClick={handleDownload}
                    style={{
                      padding: "10px 20px",
                      background: "var(--accent-success)",
                    }}
                  >
                    <Download size={16} />
                    {t("detokenize.downloadFile", { filename: fileResult.filename })}
                  </button>
                )}
              </div>

              {selectedFile.name.toLowerCase().endsWith(".pdf") && (
                <p style={S.hint}>
                  {t("detokenize.pdfNote")}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Status messages ─── */}
      {tokensReplaced > 0 && (
        <div style={S.status}>
          <CheckCircle2
            size={16}
            style={{ color: "var(--accent-success)" }}
          />
          <span>{t("detokenize.tokensReplaced", { count: tokensReplaced })}</span>
        </div>
      )}

      {unresolved.length > 0 && (
        <div style={S.warning}>
          <AlertTriangle size={16} />
          <span>
            {t("detokenize.tokensUnresolved", { count: unresolved.length, list: unresolved.join(", ") })}
          </span>
        </div>
      )}

      {error && (
        <div style={S.error}>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────
const S: Record<string, React.CSSProperties> = {
  container: {
    padding: 32,
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 16,
    overflowY: "auto",
  },
  title: { fontSize: 22, fontWeight: 700 },
  subtitle: { color: "var(--text-secondary)", fontSize: 14, maxWidth: 600 },
  tabs: { display: "flex", gap: 8 },
  tab: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 16px",
  },
  columns: { display: "flex", gap: 4, flex: 1, minHeight: 0, alignItems: "stretch" },
  column: { flex: 1, display: "flex", flexDirection: "column", gap: 8 },
  center: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    zIndex: 2,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-secondary)",
    textTransform: "uppercase" as const,
    letterSpacing: 0.5,
  },
  outputHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  textarea: {
    flex: 1,
    background: "var(--bg-surface)",
    border: "1px solid var(--border-color)",
    borderRadius: 8,
    color: "var(--text-primary)",
    padding: 16,
    fontSize: 14,
    fontFamily: "'Cascadia Code', 'Fira Code', monospace",
    lineHeight: 1.6,
    resize: "none",
    outline: "none",
  },
  fileSection: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  dropZone: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    border: "2px dashed var(--border-color)",
    borderRadius: 12,
    cursor: "pointer",
    transition: "border-color 0.2s, background 0.2s",
    padding: 40,
    color: "var(--text-secondary)",
  },
  dropZoneActive: {
    borderColor: "var(--accent-primary)",
    background: "rgba(79, 140, 255, 0.05)",
  },
  fileCard: {
    background: "var(--bg-surface)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    padding: 20,
  },
  fileInfo: { display: "flex", alignItems: "center", gap: 12 },
  hint: {
    fontSize: 12,
    color: "var(--text-tertiary)",
    marginTop: 8,
    fontStyle: "italic",
  },
  status: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13,
    color: "var(--accent-success)",
    padding: "8px 12px",
    background: "rgba(76, 175, 80, 0.1)",
    borderRadius: 6,
  },
  warning: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13,
    color: "var(--accent-warning)",
    padding: "8px 12px",
    background: "rgba(255, 152, 0, 0.1)",
    borderRadius: 6,
  },
  error: {
    fontSize: 13,
    color: "var(--accent-danger)",
    padding: "8px 12px",
    background: "rgba(244, 67, 54, 0.1)",
    borderRadius: 6,
  },
  lockMessage: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    height: "100%",
    color: "var(--text-secondary)",
  },
};
