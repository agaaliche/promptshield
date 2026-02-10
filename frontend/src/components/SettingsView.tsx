/** Settings panel — vault, LLM, detection, and app settings. */

import { useState, useEffect, useCallback } from "react";
import {
  Lock,
  Unlock,
  Brain,
  Cpu,
  Database,
  RefreshCw,
  Download,
  Upload,
  Globe,
  Zap,
} from "lucide-react";
import { useAppStore } from "../store";
import {
  unlockVault,
  getVaultStatus,
  getVaultStats,
  getLLMStatus,
  loadLLM,
  unloadLLM,
  listModels,
  getSettings,
  updateSettings,
  exportVault,
  importVault,
  configureRemoteLLM,
  testRemoteLLM,
  setLLMProvider,
} from "../api";
import type { VaultStats } from "../types";

export default function SettingsView() {
  const {
    vaultUnlocked,
    setVaultUnlocked,
    llmStatus,
    setLLMStatus,
    backendReady,
    detectionSettings,
    setDetectionSettings,
  } = useAppStore();

  const [passphrase, setPassphrase] = useState("");
  const [vaultError, setVaultError] = useState("");
  const [vaultStats, setVaultStats] = useState<VaultStats | null>(null);
  const [models, setModels] = useState<Array<{ name: string; path: string; size_gb: number }>>([]);
  const [llmError, setLlmError] = useState("");
  const [llmLoading, setLlmLoading] = useState<string | null>(null);
  const [exportPass, setExportPass] = useState("");
  const [exportStatus, setExportStatus] = useState("");
  const [importPass, setImportPass] = useState("");
  const [importStatus, setImportStatus] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [pendingNerBackend, setPendingNerBackend] = useState<string | null>(null);
  const [nerApplyStatus, setNerApplyStatus] = useState<"" | "saving" | "saved" | "error">("")
  const [nerApplyError, setNerApplyError] = useState("");

  // Remote LLM state
  const [remoteApiUrl, setRemoteApiUrl] = useState("");
  const [remoteApiKey, setRemoteApiKey] = useState("");
  const [remoteModel, setRemoteModel] = useState("");
  const [remoteStatus, setRemoteStatus] = useState<"" | "saving" | "testing" | "ok" | "error">("");
  const [remoteError, setRemoteError] = useState("");
  const [remoteLatency, setRemoteLatency] = useState<number | null>(null);

  // Load initial status
  useEffect(() => {
    if (!backendReady) return;
    getVaultStatus().then((s) => setVaultUnlocked(s.unlocked)).catch(() => {});
    getLLMStatus().then(setLLMStatus).catch(() => {});
    listModels().then(setModels).catch(() => {});
    // Hydrate detection settings from backend so persisted values are shown
    getSettings()
      .then((s) => {
        setDetectionSettings({
          regex_enabled: s.regex_enabled as boolean,
          ner_enabled: s.ner_enabled as boolean,
          llm_detection_enabled: s.llm_detection_enabled as boolean,
          ner_backend: s.ner_backend as string,
        });
        // Hydrate remote LLM fields from persisted settings
        if (s.llm_api_url) setRemoteApiUrl(s.llm_api_url as string);
        if (s.llm_api_model) setRemoteModel(s.llm_api_model as string);
        // Never show the key — just indicate it's set
        if (s.llm_api_key) setRemoteApiKey("••••••••");
      })
      .catch(() => {});
  }, [backendReady, setVaultUnlocked, setLLMStatus, setDetectionSettings]);

  useEffect(() => {
    if (vaultUnlocked) {
      getVaultStats().then(setVaultStats).catch(() => {});
    }
  }, [vaultUnlocked]);

  // ── Vault unlock ──
  const handleUnlockVault = useCallback(async () => {
    setVaultError("");
    try {
      await unlockVault(passphrase);
      setVaultUnlocked(true);
      setPassphrase("");
    } catch (e: any) {
      setVaultError(e.message || "Failed to unlock vault");
    }
  }, [passphrase, setVaultUnlocked]);

  // ── LLM load ──
  const handleLoadModel = useCallback(
    async (modelPath: string) => {
      setLlmError("");
      setLlmLoading(modelPath);
      try {
        await loadLLM(modelPath);
        const status = await getLLMStatus();
        setLLMStatus(status);
      } catch (e: any) {
        setLlmError(e.message || "Failed to load model");
      } finally {
        setLlmLoading(null);
      }
    },
    [setLLMStatus]
  );

  const handleUnloadModel = useCallback(async () => {
    try {
      await unloadLLM();
      const status = await getLLMStatus();
      setLLMStatus(status);
    } catch (e: any) {
      setLlmError(e.message);
    }
  }, [setLLMStatus]);

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>Settings</h2>

      {/* ── Vault ── */}
      <Section title="Token Vault" icon={<Database size={18} />}>
        {vaultUnlocked ? (
          <div style={styles.vaultInfo}>
            <div style={styles.badge}>
              <Unlock size={14} style={{ color: "var(--accent-success)" }} />
              <span style={{ color: "var(--accent-success)" }}>Unlocked</span>
            </div>
            {vaultStats && (
              <div style={styles.statsGrid}>
                <StatItem label="Tokens stored" value={vaultStats.total_tokens} />
                <StatItem label="Documents" value={vaultStats.total_documents} />
                <StatItem
                  label="Vault size"
                  value={`${(vaultStats.vault_size_bytes / 1024).toFixed(1)} KB`}
                />
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              <p style={{ ...styles.hint, marginBottom: 8 }}>Export all tokens as an encrypted backup file.</p>
              <div style={styles.formRow}>
                <input
                  type="password"
                  value={exportPass}
                  onChange={(e) => setExportPass(e.target.value)}
                  placeholder="Export passphrase"
                  style={{ maxWidth: 200 }}
                />
                <button
                  className="btn-ghost btn-sm"
                  disabled={!exportPass}
                  onClick={async () => {
                    try {
                      setExportStatus("");
                      const data = await exportVault(exportPass);
                      const blob = new Blob([data], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `vault-export-${Date.now()}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                      setExportStatus("Exported successfully");
                      setExportPass("");
                    } catch (e: any) {
                      setExportStatus(`Export failed: ${e.message}`);
                    }
                  }}
                >
                  <Download size={12} /> Export vault
                </button>
              </div>
              {exportStatus && (
                <p style={{ fontSize: 12, marginTop: 4, color: exportStatus.startsWith("Export f") ? "var(--accent-danger)" : "var(--accent-success)" }}>
                  {exportStatus}
                </p>
              )}
            </div>

            {/* ── Import ── */}
            <div style={{ marginTop: 16, borderTop: "1px solid var(--border-color)", paddingTop: 12 }}>
              <p style={{ ...styles.hint, marginBottom: 8 }}>Restore tokens from an encrypted backup file.</p>
              <div style={styles.formRow}>
                <label
                  className="btn-ghost btn-sm"
                  style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}
                >
                  <Upload size={12} />
                  {importFile ? importFile.name : "Choose file"}
                  <input
                    type="file"
                    accept=".json"
                    style={{ display: "none" }}
                    onChange={(e) => {
                      setImportFile(e.target.files?.[0] ?? null);
                      setImportStatus("");
                    }}
                  />
                </label>
              </div>
              {importFile && (
                <div style={{ ...styles.formRow, marginTop: 8 }}>
                  <input
                    type="password"
                    value={importPass}
                    onChange={(e) => setImportPass(e.target.value)}
                    placeholder="Export passphrase"
                    style={{ maxWidth: 200 }}
                  />
                  <button
                    className="btn-ghost btn-sm"
                    disabled={!importPass || isImporting}
                    onClick={async () => {
                      try {
                        setImportStatus("");
                        setIsImporting(true);
                        const text = await importFile.text();
                        const result = await importVault(text, importPass);
                        setImportStatus(
                          `Imported ${result.imported} token${result.imported !== 1 ? "s" : ""}` +
                          (result.skipped ? `, ${result.skipped} skipped (duplicates)` : "") +
                          (result.errors ? `, ${result.errors} errors` : "")
                        );
                        setImportFile(null);
                        setImportPass("");
                        // Refresh vault stats
                        getVaultStats().then(setVaultStats).catch(() => {});
                      } catch (e: any) {
                        setImportStatus(`Import failed: ${e.message}`);
                      } finally {
                        setIsImporting(false);
                      }
                    }}
                  >
                    {isImporting ? "Importing..." : "Restore backup"}
                  </button>
                </div>
              )}
              {importStatus && (
                <p style={{ fontSize: 12, marginTop: 4, color: importStatus.startsWith("Import f") ? "var(--accent-danger)" : "var(--accent-success)" }}>
                  {importStatus}
                </p>
              )}
            </div>
          </div>
        ) : (
          <div style={styles.vaultForm}>
            <p style={styles.hint}>
              Enter a passphrase to unlock or create the token vault.
              All token mappings are encrypted with this passphrase.
            </p>
            <div style={styles.formRow}>
              <input
                type="password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                placeholder="Vault passphrase"
                onKeyDown={(e) => e.key === "Enter" && handleUnlockVault()}
              />
              <button
                className="btn-primary"
                onClick={handleUnlockVault}
                disabled={!passphrase}
              >
                <Lock size={14} /> Unlock
              </button>
            </div>
            {vaultError && <p style={styles.errorText}>{vaultError}</p>}
          </div>
        )}
      </Section>

      {/* ── LLM ── */}
      <Section title="LLM Engine" icon={<Brain size={18} />}>
        {/* Provider toggle */}
        <div style={{ display: "flex", gap: 0, marginBottom: 16, borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-color)" }}>
          <button
            className={llmStatus?.provider === "local" || !llmStatus?.provider ? "btn-primary" : "btn-ghost"}
            style={{ flex: 1, borderRadius: 0, border: "none", padding: "8px 12px", fontSize: 13, fontWeight: 600 }}
            onClick={async () => {
              try {
                await setLLMProvider("local");
                const status = await getLLMStatus();
                setLLMStatus(status);
              } catch {}
            }}
          >
            <Cpu size={14} /> Local (GGUF)
          </button>
          <button
            className={llmStatus?.provider === "remote" ? "btn-primary" : "btn-ghost"}
            style={{ flex: 1, borderRadius: 0, border: "none", borderLeft: "1px solid var(--border-color)", padding: "8px 12px", fontSize: 13, fontWeight: 600 }}
            onClick={async () => {
              try {
                await setLLMProvider("remote");
                const status = await getLLMStatus();
                setLLMStatus(status);
              } catch {}
            }}
          >
            <Globe size={14} /> Remote API
          </button>
        </div>

        {/* ── Local LLM panel ── */}
        {(llmStatus?.provider === "local" || !llmStatus?.provider) && (
          <>
        {llmStatus?.loaded && llmStatus.provider !== "remote" ? (
          <div>
            <div style={styles.badge}>
              <Cpu size={14} style={{ color: "var(--accent-success)" }} />
              <span>{llmStatus.model_name}</span>
              {llmStatus.gpu_enabled && (
                <span style={styles.gpuTag}>GPU</span>
              )}
            </div>
            <button
              className="btn-ghost"
              onClick={handleUnloadModel}
              style={{ marginTop: 8 }}
            >
              Unload Model
            </button>
          </div>
        ) : (
          <div>
            <p style={styles.hint}>
              Load a GGUF model for enhanced PII detection. Place model files
              in the models directory.
            </p>
            <p style={{ ...styles.hint, fontSize: 11, color: "var(--text-muted)", marginTop: -4, marginBottom: 12 }}>
              For fast local inference, an NVIDIA GPU with 6+ GB VRAM
              (RTX 3060 or better) is recommended. CPU-only is very slow.
            </p>
            {models.length > 0 ? (
              <div style={styles.modelList}>
                {models.map((m) => {
                  const isActive = llmStatus?.loaded && llmStatus.provider !== "remote" && llmStatus.model_path === m.path;
                  return (
                  <div key={m.path} style={{
                    ...styles.modelItem,
                    ...(isActive ? { border: "1px solid var(--accent-primary)", background: "rgba(74, 158, 255, 0.08)" } : {}),
                  }}>
                    <div>
                      <span style={{ fontWeight: 500 }}>{m.name}</span>
                      <span style={styles.modelSize}>{m.size_gb} GB</span>
                      {isActive && <span style={{ fontSize: 11, color: "var(--accent-primary)", fontWeight: 600, marginLeft: 8 }}>● Active</span>}
                    </div>
                    {isActive ? (
                      <button
                        className="btn-ghost btn-sm"
                        onClick={handleUnloadModel}
                        disabled={llmLoading !== null}
                      >
                        Unload
                      </button>
                    ) : (
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => handleLoadModel(m.path)}
                      disabled={llmLoading !== null}
                    >
                      {llmLoading === m.path ? "Loading..." : "Load"}
                    </button>
                    )}
                  </div>
                  );
                })}
              </div>
            ) : (
              <p style={styles.hint}>
                No models found. Place .gguf files in the models directory and
                click refresh.
              </p>
            )}
            <button
              className="btn-ghost btn-sm"
              onClick={() => listModels().then(setModels)}
              style={{ marginTop: 8 }}
            >
              <RefreshCw size={12} /> Refresh models
            </button>
            {llmError && <p style={styles.errorText}>{llmError}</p>}
          </div>
        )}
          </>
        )}

        {/* ── Remote LLM panel ── */}
        {llmStatus?.provider === "remote" && (
          <div>
            <p style={styles.hint}>
              Connect to any OpenAI-compatible API — OpenAI, Anthropic (Claude),
              Groq, Mistral, Together, Azure, or your own vLLM / Ollama server.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <label style={{ fontSize: 12, color: "#888", display: "block", marginBottom: 4 }}>
                  API Base URL
                </label>
                <input
                  type="text"
                  value={remoteApiUrl}
                  onChange={(e) => { setRemoteApiUrl(e.target.value); setRemoteStatus(""); }}
                  placeholder="https://api.openai.com/v1"
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #444", background: "#1e1e1e", color: "#eee", fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "#888", display: "block", marginBottom: 4 }}>
                  API Key
                </label>
                <input
                  type="password"
                  value={remoteApiKey}
                  onChange={(e) => { setRemoteApiKey(e.target.value); setRemoteStatus(""); }}
                  placeholder="sk-..."
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #444", background: "#1e1e1e", color: "#eee", fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "#888", display: "block", marginBottom: 4 }}>
                  Model name
                </label>
                <input
                  type="text"
                  value={remoteModel}
                  onChange={(e) => { setRemoteModel(e.target.value); setRemoteStatus(""); }}
                  placeholder="gpt-4o-mini"
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #444", background: "#1e1e1e", color: "#eee", fontSize: 13 }}
                />
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                  Examples: gpt-4o-mini, claude-sonnet-4-20250514, llama-3.1-70b-versatile, mistral-large-latest
                </p>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button
                  className="btn-primary btn-sm"
                  disabled={!remoteApiUrl || !remoteApiKey || !remoteModel || remoteStatus === "saving"}
                  onClick={async () => {
                    setRemoteStatus("saving");
                    setRemoteError("");
                    try {
                      // If user typed a masked key, don't send it
                      const keyToSend = remoteApiKey.startsWith("••") ? "" : remoteApiKey;
                      if (!keyToSend) {
                        setRemoteStatus("error");
                        setRemoteError("Please enter a valid API key");
                        return;
                      }
                      await configureRemoteLLM(remoteApiUrl, keyToSend, remoteModel);
                      const status = await getLLMStatus();
                      setLLMStatus(status);
                      setRemoteStatus("ok");
                      setRemoteApiKey("••••••••"); // mask after save
                      setTimeout(() => setRemoteStatus(""), 3000);
                    } catch (e: any) {
                      setRemoteStatus("error");
                      setRemoteError(e.message || "Failed to configure remote LLM");
                    }
                  }}
                >
                  {remoteStatus === "saving" ? "Saving..." : "Save & Activate"}
                </button>
                <button
                  className="btn-ghost btn-sm"
                  disabled={remoteStatus === "testing" || !llmStatus?.remote_api_url}
                  onClick={async () => {
                    setRemoteStatus("testing");
                    setRemoteError("");
                    setRemoteLatency(null);
                    try {
                      const result = await testRemoteLLM();
                      if (result.ok) {
                        setRemoteStatus("ok");
                        setRemoteLatency(result.latency_ms ?? null);
                      } else {
                        setRemoteStatus("error");
                        setRemoteError(result.error || "Connection test failed");
                      }
                    } catch (e: any) {
                      setRemoteStatus("error");
                      setRemoteError(e.message || "Test failed");
                    }
                  }}
                >
                  <Zap size={12} /> {remoteStatus === "testing" ? "Testing..." : "Test connection"}
                </button>
              </div>

              {remoteStatus === "ok" && (
                <p style={{ fontSize: 12, color: "var(--accent-success)", display: "flex", alignItems: "center", gap: 4 }}>
                  ✓ Connected{remoteLatency != null && ` — ${remoteLatency}ms latency`}
                </p>
              )}
              {remoteStatus === "error" && (
                <p style={{ fontSize: 12, color: "var(--accent-danger)" }}>{remoteError}</p>
              )}

              {llmStatus?.remote_model && (
                <div style={{ ...styles.badge, marginTop: 4 }}>
                  <Globe size={14} style={{ color: "var(--accent-primary)" }} />
                  <span>{llmStatus.remote_model}</span>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>@ {llmStatus.remote_api_url}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </Section>

      {/* ── Detection settings ── */}
      <Section title="Detection" icon={<span>🔍</span>}>
        <p style={styles.hint}>
          Detection uses a 3-layer hybrid pipeline: Regex patterns → NER (spaCy or BERT) → LLM ({llmStatus?.provider === "remote" ? "Remote API" : "Local"}).
          The LLM layer is optional and requires a loaded model or configured remote API.
        </p>
        <div style={styles.checkboxGroup}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={detectionSettings.regex_enabled}
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ regex_enabled: v });
                updateSettings({ regex_enabled: v }).catch(() => {});
              }}
            />{" "}
            Regex patterns (SSN, email, phone, etc.)
          </label>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={detectionSettings.ner_enabled}
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ ner_enabled: v });
                updateSettings({ ner_enabled: v }).catch(() => {});
              }}
            />{" "}
            NER model (names, organizations, locations)
          </label>

          {detectionSettings.ner_enabled && (
            <div style={{ marginLeft: 24, marginTop: 4, marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: "#888", display: "block", marginBottom: 4 }}>
                NER backend
              </label>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select
                  value={pendingNerBackend ?? detectionSettings.ner_backend}
                  onChange={(e) => {
                    setPendingNerBackend(e.target.value);
                    setNerApplyStatus("");
                  }}
                  style={{
                    flex: 1,
                    padding: "6px 8px",
                    borderRadius: 6,
                    border: "1px solid #444",
                    background: "#1e1e1e",
                    color: "#eee",
                    fontSize: 13,
                  }}
                >
                  <option value="spacy">spaCy (local, no download required)</option>
                  <option value="dslim/bert-base-NER">BERT-base NER — general entities</option>
                  <option value="StanfordAIMI/stanford-deidentifier-base">Stanford De-identifier — clinical / medical</option>
                  <option value="lakshyakh93/deberta_finetuned_pii">DeBERTa PII — names, emails, phones, addresses</option>
                  <option value="iiiorg/piiranha-v1-detect-personal-information">Piiranha — multilingual PII (93% F1, 6 languages)</option>
                  <option value="Isotonic/distilbert_finetuned_ai4privacy_v2">DistilBERT AI4Privacy — fast PII (95% F1, 54 types)</option>
                </select>
                <button
                  className="btn-primary btn-sm"
                  disabled={
                    !pendingNerBackend ||
                    pendingNerBackend === detectionSettings.ner_backend ||
                    nerApplyStatus === "saving"
                  }
                  onClick={async () => {
                    if (!pendingNerBackend) return;
                    setNerApplyStatus("saving");
                    setNerApplyError("");
                    try {
                      await updateSettings({ ner_backend: pendingNerBackend });
                      setDetectionSettings({ ner_backend: pendingNerBackend });
                      setPendingNerBackend(null);
                      setNerApplyStatus("saved");
                      setTimeout(() => setNerApplyStatus(""), 3000);
                    } catch (e: any) {
                      setNerApplyStatus("error");
                      setNerApplyError(e.message || "Failed to update NER backend");
                    }
                  }}
                  style={{ whiteSpace: "nowrap" }}
                >
                  {nerApplyStatus === "saving" ? "Applying..." : "Apply"}
                </button>
              </div>
              {nerApplyStatus === "saved" && (
                <p style={{ fontSize: 12, color: "var(--accent-success)", marginTop: 4 }}>
                  NER backend updated — active for the next detection run.
                </p>
              )}
              {nerApplyStatus === "error" && (
                <p style={{ fontSize: 12, color: "var(--accent-danger)", marginTop: 4 }}>
                  {nerApplyError}
                </p>
              )}
            </div>
          )}
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={detectionSettings.llm_detection_enabled}
              disabled={!llmStatus?.loaded}
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ llm_detection_enabled: v });
                updateSettings({ llm_detection_enabled: v }).catch(() => {});
              }}
            />{" "}
            LLM contextual analysis {!llmStatus?.loaded && "(configure LLM first)"}
          </label>
        </div>
      </Section>
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        {icon}
        <h3 style={{ fontSize: 15, fontWeight: 600 }}>{title}</h3>
      </div>
      <div style={styles.sectionBody}>{children}</div>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={styles.statItem}>
      <span style={styles.statValue}>{value}</span>
      <span style={styles.statLabel}>{label}</span>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 32,
    height: "100%",
    overflowY: "auto",
    maxWidth: 700,
  },
  title: { fontSize: 22, fontWeight: 700, marginBottom: 24 },
  section: {
    background: "var(--bg-surface)",
    borderRadius: 8,
    marginBottom: 16,
    border: "1px solid var(--border-color)",
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "12px 16px",
    borderBottom: "1px solid var(--border-color)",
    color: "var(--text-primary)",
  },
  sectionBody: { padding: 16 },
  hint: {
    fontSize: 13,
    color: "var(--text-secondary)",
    marginBottom: 12,
    lineHeight: 1.5,
  },
  formRow: { display: "flex", gap: 8, alignItems: "center" },
  errorText: { color: "var(--accent-danger)", fontSize: 13, marginTop: 8 },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    fontSize: 13,
    fontWeight: 500,
    padding: "4px 10px",
    background: "var(--bg-primary)",
    borderRadius: 4,
  },
  gpuTag: {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--accent-success)",
    background: "rgba(76, 175, 80, 0.15)",
    padding: "1px 6px",
    borderRadius: 3,
  },
  vaultInfo: { display: "flex", flexDirection: "column", gap: 12 },
  vaultForm: {},
  statsGrid: { display: "flex", gap: 16, marginTop: 8 },
  statItem: {
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-primary)",
    padding: "8px 16px",
    borderRadius: 6,
    minWidth: 100,
  },
  statValue: { fontSize: 18, fontWeight: 700 },
  statLabel: { fontSize: 11, color: "var(--text-muted)" },
  modelList: { display: "flex", flexDirection: "column", gap: 8 },
  modelItem: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 12px",
    background: "var(--bg-primary)",
    borderRadius: 6,
  },
  modelSize: { fontSize: 12, color: "var(--text-muted)", marginLeft: 8 },
  checkboxGroup: { display: "flex", flexDirection: "column", gap: 8 },
  checkboxLabel: {
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    gap: 8,
    color: "var(--text-secondary)",
    cursor: "pointer",
  },
};
