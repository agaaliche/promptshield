/** De-tokenization view — paste text OR upload a file to replace tokens with originals. */

import { useState, useCallback, useRef } from "react";
import {
  ArrowRightLeft,
  Copy,
  AlertTriangle,
  CheckCircle2,
  Upload,
  FileText,
  Download,
  X,
} from "lucide-react";
import { detokenize, detokenizeFile, type DetokenizeFileResult } from "../api";
import { useAppStore } from "../store";

type Mode = "text" | "file";

const ACCEPTED_EXTENSIONS = ".txt,.csv,.pdf,.docx,.xlsx";

export default function DetokenizeView() {
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

  const { vaultUnlocked, isProcessing, setIsProcessing } = useAppStore();

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
    } catch (e: any) {
      setError(e.message || "De-tokenization failed");
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
    } catch (e: any) {
      setError(e.message || "File de-tokenization failed");
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

  // ── Vault locked guard ────────────────────────────────────────────
  if (!vaultUnlocked) {
    return (
      <div style={S.container}>
        <div style={S.lockMessage}>
          <AlertTriangle size={48} style={{ color: "var(--accent-warning)" }} />
          <h2>Vault Locked</h2>
          <p>Unlock the vault in Settings to use de-tokenization.</p>
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div style={S.container}>
      <h2 style={S.title}>De-tokenize</h2>
      <p style={S.subtitle}>
        Replace anonymization tokens with original values from your vault.
      </p>

      {/* Mode tabs */}
      <div style={S.tabs}>
        <button
          className={mode === "text" ? "btn-primary" : "btn-ghost"}
          style={S.tab}
          onClick={() => setMode("text")}
        >
          <FileText size={14} /> Paste Text
        </button>
        <button
          className={mode === "file" ? "btn-primary" : "btn-ghost"}
          style={S.tab}
          onClick={() => setMode("file")}
        >
          <Upload size={14} /> Upload File
        </button>
      </div>

      {/* ─── TEXT MODE ─── */}
      {mode === "text" && (
        <div style={S.columns}>
          <div style={S.column}>
            <label style={S.label}>Input (with tokens)</label>
            <textarea
              style={S.textarea}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Paste text containing [ANON_PERSON_A3F2B1] style tokens here..."
              rows={18}
            />
          </div>

          <div style={S.center}>
            <button
              className="btn-primary"
              onClick={handleDetokenizeText}
              disabled={isProcessing || !input.trim()}
              style={{ padding: "10px 20px" }}
            >
              <ArrowRightLeft size={16} />
              {isProcessing ? "Processing..." : "De-tokenize"}
            </button>
          </div>

          <div style={S.column}>
            <div style={S.outputHeader}>
              <label style={S.label}>Output (restored)</label>
              {output && (
                <button className="btn-ghost btn-sm" onClick={copyOutput}>
                  <Copy size={12} /> Copy
                </button>
              )}
            </div>
            <textarea
              style={S.textarea}
              value={output}
              readOnly
              placeholder="De-tokenized text will appear here..."
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
                Drop a file here or click to browse
              </p>
              <p
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: "var(--text-tertiary)",
                }}
              >
                Supported: .pdf, .docx, .xlsx, .txt, .csv
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
                  {isProcessing ? "Processing..." : "De-tokenize File"}
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
                    Download {fileResult.filename}
                  </button>
                )}
              </div>

              {selectedFile.name.toLowerCase().endsWith(".pdf") && (
                <p style={S.hint}>
                  Note: PDF files will be converted to .txt for
                  de-tokenization because modifying PDF internals is
                  unreliable.
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
          <span>{tokensReplaced} token(s) replaced successfully</span>
        </div>
      )}

      {unresolved.length > 0 && (
        <div style={S.warning}>
          <AlertTriangle size={16} />
          <span>
            {unresolved.length} token(s) could not be resolved:{" "}
            {unresolved.join(", ")}
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
  columns: { display: "flex", gap: 16, flex: 1, minHeight: 0 },
  column: { flex: 1, display: "flex", flexDirection: "column", gap: 8 },
  center: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
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
