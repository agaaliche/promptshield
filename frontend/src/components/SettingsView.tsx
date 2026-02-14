/** Settings panel — vault, LLM, detection, and app settings. */

import { useState, useEffect, useCallback, useRef } from "react";
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
  FolderOpen,
  Trash2,
  ChevronDown,
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
  openModelsDir,
  getSettings,
  updateSettings,
  exportVault,
  importVault,
  configureRemoteLLM,
  disconnectRemoteLLM,
  testRemoteLLM,
  setLLMProvider,
  getHardwareInfo,
} from "../api";
import { logError } from "../api";
import type { HardwareInfo } from "../api";
import type { VaultStats } from "../types";

const NER_MODELS = [
  { value: "auto", label: "Auto — best model per language (recommended)", lang: "Auto", languages: "English, Spanish, French, German, Italian, Dutch" },
  { value: "spacy", label: "Default — fast, works offline, no download", lang: "English" },
  { value: "dslim/bert-base-NER", label: "General purpose — good all-around", lang: "English" },
  { value: "StanfordAIMI/stanford-deidentifier-base", label: "Medical & clinical — healthcare documents", lang: "English" },
  { value: "lakshyakh93/deberta_finetuned_pii", label: "Personal info — names, emails, phones, addresses", lang: "English" },
  { value: "iiiorg/piiranha-v1-detect-personal-information", label: "Multilingual — 6 languages, high accuracy", lang: "Multilingual", languages: "English, German, French, Spanish, Italian, Dutch" },
  { value: "Isotonic/distilbert_finetuned_ai4privacy_v2", label: "Comprehensive — 54 data types, very fast", lang: "English", languages: "Covers 54 PII types including names, financial, identity, addresses, and more" },
] as const;

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
  const [nerDropOpen, setNerDropOpen] = useState(false);
  const nerDropRef = useRef<HTMLDivElement>(null);

  // Remote LLM state
  const [remoteApiUrl, setRemoteApiUrl] = useState("");
  const [remoteApiKey, setRemoteApiKey] = useState("");
  const [remoteModel, setRemoteModel] = useState("");
  const [remoteStatus, setRemoteStatus] = useState<"" | "saving" | "testing" | "ok" | "error">("");
  const [remoteError, setRemoteError] = useState("");
  const [remoteLatency, setRemoteLatency] = useState<number | null>(null);
  const [hwInfo, setHwInfo] = useState<HardwareInfo | null>(null);

  // Load initial status
  useEffect(() => {
    if (!backendReady) return;
    getVaultStatus().then((s) => setVaultUnlocked(s.unlocked)).catch(logError("vault-status"));
    listModels().then(setModels).catch(logError("list-models"));
    getHardwareInfo().then(setHwInfo).catch(logError("hw-info"));
    // Hydrate settings + LLM status together so we can validate llm_detection_enabled
    Promise.all([getSettings(), getLLMStatus()])
      .then(([s, status]) => {
        setLLMStatus(status);
        const hasValidLlm =
          status.loaded ||
          (status.provider === "remote" && !!status.remote_api_url && !!status.remote_model);
        const llmEnabled = (s.llm_detection_enabled as boolean) && hasValidLlm;
        setDetectionSettings({
          regex_enabled: s.regex_enabled as boolean,
          ner_enabled: s.ner_enabled as boolean,
          llm_detection_enabled: llmEnabled,
          ner_backend: s.ner_backend as string,
          detection_fuzziness: (s.detection_fuzziness as number) ?? 0.5,
          detection_language: (s.detection_language as string) ?? "auto",
        });
        // Persist the corrected value if it changed
        if (s.llm_detection_enabled && !hasValidLlm) {
          updateSettings({ llm_detection_enabled: false }).catch(logError("update-settings"));
        }
        // Hydrate remote LLM fields from persisted settings
        if (s.llm_api_url) setRemoteApiUrl(s.llm_api_url as string);
        if (s.llm_api_model) setRemoteModel(s.llm_api_model as string);
        // Never show the key — just indicate it's set
        if (s.llm_api_key) setRemoteApiKey("••••••••");
      })
      .catch(logError("load-settings"));
  }, [backendReady, setVaultUnlocked, setLLMStatus, setDetectionSettings]);

  useEffect(() => {
    if (vaultUnlocked) {
      getVaultStats().then(setVaultStats).catch(logError("vault-stats"));
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

  // Minimum hardware for local LLM: GPU with 4+ GB VRAM required
  const localLlmReady = hwInfo
    ? hwInfo.gpus.length > 0 && Math.max(...hwInfo.gpus.map(g => g.vram_total_mb)) >= 4096
    : null; // null = still loading, don't block yet

  // Auto-unload local LLM if hardware is insufficient
  useEffect(() => {
    if (localLlmReady === false && llmStatus?.loaded && llmStatus.provider !== "remote") {
      unloadLLM().then(() => getLLMStatus().then(setLLMStatus)).catch(logError("unload-llm"));
    }
  }, [localLlmReady, llmStatus?.loaded, llmStatus?.provider, setLLMStatus]);

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
                <p style={{ fontSize: 12, marginTop: 4, color: exportStatus.toLowerCase().includes("failed") ? "var(--accent-danger)" : "var(--accent-success)" }}>
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
                        getVaultStats().then(setVaultStats).catch(logError("vault-stats"));
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
                <p style={{ fontSize: 12, marginTop: 4, color: importStatus.toLowerCase().includes("failed") ? "var(--accent-danger)" : "var(--accent-success)" }}>
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

      {/* ── Detection settings ── */}
      <Section title="Detection" icon={<span>🔍</span>}>
        <p style={styles.hint}>
          Choose which methods are used to find personal information in your documents.
        </p>
        <div style={styles.checkboxGroup}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={detectionSettings.regex_enabled}
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ regex_enabled: v });
                updateSettings({ regex_enabled: v }).catch(logError("update-settings"));
              }}
            />{" "}
            Pattern matching (finds IDs, emails, phone numbers, etc.)
          </label>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={detectionSettings.ner_enabled}
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ ner_enabled: v });
                updateSettings({ ner_enabled: v }).catch(logError("update-settings"));
              }}
            />{" "}
            AI recognition (finds names, organizations, locations)
          </label>

          {detectionSettings.ner_enabled && (
            <div style={{ marginLeft: 24, marginTop: 4, marginBottom: 8 }}>
              <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                AI recognition model
              </label>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <div ref={nerDropRef} style={{ flex: 1, position: "relative" }}>
                  {/* Custom dropdown trigger */}
                  <button
                    type="button"
                    onClick={() => setNerDropOpen(!nerDropOpen)}
                    onBlur={(e) => {
                      if (!nerDropRef.current?.contains(e.relatedTarget as Node)) setNerDropOpen(false);
                    }}
                    style={{
                      width: "100%",
                      padding: "6px 8px",
                      borderRadius: 6,
                      border: "1px solid var(--border-color)",
                      background: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                      fontSize: 13,
                      textAlign: "left",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {(NER_MODELS.find(m => m.value === (pendingNerBackend ?? detectionSettings.ner_backend)) ?? NER_MODELS[0]).label}
                    </span>
                    {(() => {
                      const sel = NER_MODELS.find(m => m.value === (pendingNerBackend ?? detectionSettings.ner_backend)) ?? NER_MODELS[0];
                      const isAuto = sel.lang === "Auto";
                      const isMulti = sel.lang === "Multilingual";
                      return (
                        <span style={{
                          fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                          ...(isAuto ? { background: "rgba(76,175,80,0.15)", color: "var(--accent-success)" } : isMulti ? { background: "rgba(74,158,255,0.12)", color: "var(--accent-primary)" } : { background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }),
                        }}>{sel.lang}</span>
                      );
                    })()}
                    <ChevronDown size={14} style={{ flexShrink: 0, color: "var(--text-muted)", transition: "transform 0.15s", transform: nerDropOpen ? "rotate(180deg)" : "none" }} />
                  </button>
                  {/* Dropdown list */}
                  {nerDropOpen && (
                    <div style={{
                      position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0,
                      background: "var(--bg-secondary)", border: "1px solid var(--border-color)", borderRadius: 6,
                      zIndex: 50, maxHeight: 260, overflowY: "auto",
                      boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    }}>
                      {NER_MODELS.map((m) => {
                        const selected = m.value === (pendingNerBackend ?? detectionSettings.ner_backend);
                        const isAuto = m.lang === "Auto";
                        const isMulti = m.lang === "Multilingual";
                        return (
                          <button
                            key={m.value}
                            type="button"
                            onClick={() => { setPendingNerBackend(m.value); setNerApplyStatus(""); setNerDropOpen(false); }}
                            style={{
                              width: "100%", padding: "8px 10px",
                              background: selected ? "rgba(74,158,255,0.1)" : "transparent",
                              border: "none", color: "var(--text-primary)", fontSize: 13, textAlign: "left",
                              cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                              borderBottom: m.value === "auto" ? "1px solid rgba(255,255,255,0.10)" : "1px solid rgba(255,255,255,0.04)",
                            }}
                            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = selected ? "rgba(74,158,255,0.15)" : "rgba(255,255,255,0.05)"; }}
                            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = selected ? "rgba(74,158,255,0.1)" : "transparent"; }}
                          >
                            <span style={{ flex: 1 }}>{m.label}</span>
                            <span style={{
                              fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                              ...(isAuto ? { background: "rgba(76,175,80,0.15)", color: "var(--accent-success)" } : isMulti ? { background: "rgba(74,158,255,0.12)", color: "var(--accent-primary)" } : { background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }),
                            }}>{m.lang}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
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
              {(() => {
                const sel = pendingNerBackend ?? detectionSettings.ner_backend;
                const model = NER_MODELS.find(m => m.value === sel);
                if (sel === "auto") {
                  return (
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                      🧠 Detects document language automatically and picks the best model.
                      <br />🌐 Supported: English, Spanish, French, German, Italian, Dutch
                    </p>
                  );
                }
                return model && "languages" in model ? (
                  <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
                    🌐 {model.languages}
                  </p>
                ) : null;
              })()}
              {nerApplyStatus === "saved" && (
                <p style={{ fontSize: 12, color: "var(--accent-success)", marginTop: 4 }}>
                  Model updated — takes effect on next scan.
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
              onChange={(e) => {
                const v = e.target.checked;
                setDetectionSettings({ llm_detection_enabled: v });
                updateSettings({ llm_detection_enabled: v }).catch(logError("update-settings"));
              }}
            />{" "}
            Deep analysis (uses an LLM for harder-to-find information)
          </label>

          {/* Detection language selector */}
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <span style={{ fontSize: 13, color: "var(--text-primary)" }}>
                Detection language
              </span>
            </div>
            <select
              value={detectionSettings.detection_language ?? "auto"}
              onChange={async (e) => {
                const v = e.target.value;
                setDetectionSettings({ detection_language: v });
                try {
                  await updateSettings({ detection_language: v });
                } catch (err: any) {
                  console.error("Failed to update detection language:", err);
                }
              }}
              style={{
                width: "100%",
                padding: "6px 8px",
                borderRadius: 6,
                border: "1px solid var(--border-color)",
                background: "var(--bg-secondary)",
                color: "var(--text-primary)",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              <option value="auto">Auto-detect per page</option>
              <option value="en">English</option>
              <option value="fr">French</option>
              <option value="de">German</option>
              <option value="es">Spanish</option>
              <option value="it">Italian</option>
              <option value="nl">Dutch</option>
            </select>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
              Filters regex patterns to only those relevant for the selected
              language. &ldquo;Auto&rdquo; detects per page using stop-word analysis.
            </p>
          </div>

          {/* Detection fuzziness slider */}
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <span style={{ fontSize: 13, color: "var(--text-primary)" }}>
                Region grouping
              </span>
              <span style={{ fontSize: 12, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                {Math.round(detectionSettings.detection_fuzziness * 100)}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(detectionSettings.detection_fuzziness * 100)}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10) / 100;
                setDetectionSettings({ detection_fuzziness: v });
              }}
              onMouseUp={() => {
                updateSettings({ detection_fuzziness: detectionSettings.detection_fuzziness })
                  .catch(logError("update-settings"));
              }}
              onTouchEnd={() => {
                updateSettings({ detection_fuzziness: detectionSettings.detection_fuzziness })
                  .catch(logError("update-settings"));
              }}
              style={{ width: "100%", accentColor: "var(--accent-primary)" }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
              <span>Strict — split more</span>
              <span>Permissive — group more</span>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
              Controls how aggressively nearby words merge into a single
              highlight. Higher values allow wider gaps between words in
              the same region (capped at 20 pt regardless).
            </p>
          </div>
        </div>
      </Section>

      {/* ── LLM Engine ── */}
      {detectionSettings.llm_detection_enabled && (
      <Section title="LLM Engine" icon={<Brain size={18} />}>
        {/* Hardware info */}
        {hwInfo && (
          <div style={{ marginBottom: 16, padding: "10px 12px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: "1px solid var(--border-color)", fontSize: 12, lineHeight: 1.6 }}>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap", color: "var(--text-secondary)" }}>
              <span title={hwInfo.cpu.name}><Cpu size={13} style={{ verticalAlign: -2, marginRight: 4 }} />{hwInfo.cpu.cores_physical}c/{hwInfo.cpu.cores_logical}t</span>
              <span>RAM {hwInfo.ram.total_gb} GB</span>
              {hwInfo.gpus.length > 0 ? hwInfo.gpus.map((gpu, i) => (
                <span key={i} style={{ color: "var(--accent-success)" }} title={`${gpu.name} — Driver ${gpu.driver_version}`}>
                  <Zap size={13} style={{ verticalAlign: -2, marginRight: 3 }} />
                  {gpu.name} — {Math.round(gpu.vram_total_mb / 1024)} GB VRAM ({Math.round(gpu.vram_free_mb / 1024)} GB free)
                </span>
              )) : (
                <span style={{ color: "var(--text-muted)" }}>No GPU detected — CPU only</span>
              )}
            </div>
          </div>
        )}
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
            {localLlmReady === false ? (
              <div style={{ padding: "10px 12px", marginBottom: 12, background: "rgba(244,67,54,0.08)", borderRadius: 6, border: "1px solid rgba(244,67,54,0.2)", fontSize: 12, color: "var(--accent-danger)", lineHeight: 1.6 }}>
                <strong>Local LLM disabled</strong> — minimum hardware requirements not met.
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                  Requires an NVIDIA GPU with 4+ GB VRAM, or at least 16 GB RAM.
                  Use <strong style={{ color: "var(--text-secondary)" }}>Remote API</strong> instead to connect to an external LLM service.
                </div>
              </div>
            ) : (
              <p style={styles.hint}>
                Load a GGUF model for enhanced PII detection. Place model files
                in the models directory.
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => openModelsDir().catch(logError("open-models-dir"))}
                  style={{ marginLeft: 4, display: "inline-flex", alignItems: "center", gap: 4, verticalAlign: "middle", fontSize: 11, padding: "2px 6px" }}
                  title="Open models directory"
                >
                  <FolderOpen size={12} /> Open
                </button>
              </p>
            )}

            {models.length > 0 ? (
              <div style={styles.modelList}>
                {models.map((m) => {
                  const isActive = llmStatus?.loaded && llmStatus.provider !== "remote" && llmStatus.model_path === m.path;
                  const disabled = localLlmReady === false;
                  return (
                  <div key={m.path} style={{
                    ...styles.modelItem,
                    ...(isActive ? { border: "1px solid var(--accent-primary)", background: "rgba(74, 158, 255, 0.08)" } : {}),
                    ...(disabled ? { opacity: 0.45 } : {}),
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
                      disabled={llmLoading !== null || disabled}
                    >
                      {llmLoading === m.path ? "Loading..." : "Load"}
                    </button>
                    )}
                  </div>
                  );
                })}
              </div>
            ) : localLlmReady !== false ? (
              <p style={styles.hint}>
                No models found. Place .gguf files in the models directory and
                click refresh.
              </p>
            ) : null}
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
                <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  API Base URL
                </label>
                <input
                  type="text"
                  value={remoteApiUrl}
                  onChange={(e) => { setRemoteApiUrl(e.target.value); setRemoteStatus(""); }}
                  placeholder="https://api.openai.com/v1"
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  API Key
                </label>
                <input
                  type="password"
                  value={remoteApiKey}
                  onChange={(e) => { setRemoteApiKey(e.target.value); setRemoteStatus(""); }}
                  placeholder="sk-..."
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                  Model name
                </label>
                <input
                  type="text"
                  value={remoteModel}
                  onChange={(e) => { setRemoteModel(e.target.value); setRemoteStatus(""); }}
                  placeholder="gpt-4o-mini"
                  style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
                />
                <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                  Examples: gpt-4o-mini, claude-sonnet-4-20250514, llama-3.1-70b-versatile, mistral-large-latest
                </p>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 4, alignItems: "center" }}>
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
                {llmStatus?.remote_api_url && (
                  <button
                    className="btn-ghost btn-sm"
                    style={{ marginLeft: "auto", color: "var(--accent-danger)", padding: 4, lineHeight: 1 }}
                    title="Remove connection"
                    onClick={async () => {
                      try {
                        await disconnectRemoteLLM();
                        const status = await getLLMStatus();
                        setLLMStatus(status);
                        setRemoteApiUrl("");
                        setRemoteApiKey("");
                        setRemoteModel("");
                        setRemoteStatus("");
                        setRemoteError("");
                        if (detectionSettings.llm_detection_enabled && !status.loaded) {
                          setDetectionSettings({ llm_detection_enabled: false });
                          updateSettings({ llm_detection_enabled: false }).catch(logError("update-settings"));
                        }
                      } catch (e: any) {
                        setRemoteError(e.message || "Failed to remove connection");
                      }
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
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
      )}

      {/* ── License ── */}
      <LicenseSection />
    </div>
  );
}

function LicenseSection() {
  const { licenseStatus, autoValidateOnline, setAutoValidateOnline, addSnackbar, setLicenseStatus, setLicenseChecked } = useAppStore();
  const [deactivating, setDeactivating] = useState(false);

  const payload = licenseStatus?.payload;

  const handleDeactivate = async () => {
    setDeactivating(true);
    try {
      const { deactivateLicense } = await import("../licenseApi");
      await deactivateLicense();
      addSnackbar("License deactivated", "info");
    } catch {
      addSnackbar("Failed to deactivate license", "error");
    } finally {
      setDeactivating(false);
    }
  };

  const planLabel =
    payload?.plan === "free_trial" ? "Free Trial"
    : payload?.plan === "pro" ? "Pro"
    : payload?.plan ?? "—";

  const statusColor = licenseStatus?.valid
    ? (licenseStatus.days_remaining !== null && licenseStatus.days_remaining <= 7
        ? "#d29922"
        : "#3fb950")
    : "#f85149";

  return (
    <Section title="License" icon={<Lock size={16} />}>
      {payload && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor, flexShrink: 0 }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>{planLabel}</span>
            {licenseStatus?.days_remaining !== null && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
                {licenseStatus.days_remaining}d remaining
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 4 }}>
            <span>Email: {payload.email}</span>
            <span>Seats: {payload.seats}</span>
            <span>Expires: {new Date(payload.expires).toLocaleDateString()}</span>
          </div>
        </div>
      )}

      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={autoValidateOnline}
            onChange={(e) => setAutoValidateOnline(e.target.checked)}
          />
          Automatically validate license online
        </label>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, lineHeight: 1.4 }}>
          When enabled, the app silently refreshes your license key on launch when internet is available.
          Your key works offline for up to 30 days between validations.
        </p>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <button
          onClick={handleDeactivate}
          disabled={deactivating}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: 12,
            cursor: "pointer",
          }}
        >
          {deactivating ? "Deactivating..." : "Deactivate License"}
        </button>
        <a
          href="https://promptshield.ca"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--accent-primary)",
            fontSize: 12,
            cursor: "pointer",
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <Globe size={12} /> Manage Account
        </a>
      </div>
    </Section>
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
