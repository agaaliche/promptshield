/** LLM Engine — hardware info, local/remote provider toggle, model list, remote API config. */

import { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  Cpu,
  Globe,
  Zap,
  FolderOpen,
  Trash2,
  RefreshCw,
} from "../../icons";
import { useDetectionStore } from "../../store";
import { toErrorMessage } from "../../errorUtils";
import {
  getLLMStatus,
  loadLLM,
  unloadLLM,
  listModels,
  openModelsDir,
  updateSettings,
  configureRemoteLLM,
  disconnectRemoteLLM,
  testRemoteLLM,
  setLLMProvider,
  getHardwareInfo,
  logError,
} from "../../api";
import type { HardwareInfo } from "../../api";
import { Section, styles } from "./settingsStyles";

export default function LLMEngineSection() {
  const { t } = useTranslation();
  const { llmStatus, setLLMStatus, detectionSettings, setDetectionSettings } = useDetectionStore();

  const [models, setModels] = useState<Array<{ name: string; path: string; size_gb: number }>>([]);
  const [llmError, setLlmError] = useState("");
  const [llmLoading, setLlmLoading] = useState<string | null>(null);

  // Remote LLM state
  const [remoteApiUrl, setRemoteApiUrl] = useState("");
  const [remoteApiKey, setRemoteApiKey] = useState("");
  const [remoteModel, setRemoteModel] = useState("");
  const [remoteStatus, setRemoteStatus] = useState<"" | "saving" | "testing" | "ok" | "error">("");
  const [remoteError, setRemoteError] = useState("");
  const [remoteLatency, setRemoteLatency] = useState<number | null>(null);
  const [hwInfo, setHwInfo] = useState<HardwareInfo | null>(null);

  // Load models + hardware info on mount
  useEffect(() => {
    listModels().then(setModels).catch(logError("list-models"));
    getHardwareInfo().then(setHwInfo).catch(logError("hw-info"));
  }, []);

  // Hydrate remote LLM fields from status
  useEffect(() => {
    if (llmStatus?.remote_api_url && !remoteApiUrl) setRemoteApiUrl(llmStatus.remote_api_url);
    if (llmStatus?.remote_model && !remoteModel) setRemoteModel(llmStatus.remote_model);
  }, [llmStatus, remoteApiUrl, remoteModel]);

  // Minimum hardware for local LLM: GPU with 4+ GB VRAM or 16+ GB system RAM
  const localLlmReady = hwInfo
    ? (hwInfo.gpus.length > 0 && Math.max(...hwInfo.gpus.map(g => g.vram_total_mb)) >= 4096)
      || hwInfo.ram.total_gb >= 16
    : null;

  // Auto-unload local LLM if hardware is insufficient
  useEffect(() => {
    if (localLlmReady === false && llmStatus?.loaded && llmStatus.provider !== "remote") {
      unloadLLM().then(() => getLLMStatus().then(setLLMStatus)).catch(logError("unload-llm"));
    }
  }, [localLlmReady, llmStatus?.loaded, llmStatus?.provider, setLLMStatus]);

  const handleLoadModel = useCallback(
    async (modelPath: string) => {
      setLlmError("");
      setLlmLoading(modelPath);
      try {
        await loadLLM(modelPath);
        const status = await getLLMStatus();
        setLLMStatus(status);
      } catch (e: unknown) {
        setLlmError(toErrorMessage(e) || t("llmEngine.loadFailed"));
      } finally {
        setLlmLoading(null);
      }
    },
    [setLLMStatus, t]
  );

  const handleUnloadModel = useCallback(async () => {
    try {
      await unloadLLM();
      const status = await getLLMStatus();
      setLLMStatus(status);
    } catch (e: unknown) {
      setLlmError(toErrorMessage(e));
    }
  }, [setLLMStatus]);

  return (
    <Section>
      {/* Hardware info */}
      {hwInfo && (
        <div style={{ marginBottom: 16, padding: "10px 12px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: "1px solid var(--border-color)", fontSize: 12, lineHeight: 1.6 }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", color: "var(--text-secondary)" }}>
            <span title={hwInfo.cpu.name}><Cpu size={13} style={{ verticalAlign: -2, marginRight: 4 }} />{hwInfo.cpu.cores_physical}c/{hwInfo.cpu.cores_logical}t</span>
            <span>RAM {hwInfo.ram.total_gb} GB</span>
            {hwInfo.gpus.length > 0 ? hwInfo.gpus.map((gpu, i) => (
              <span key={i} style={{ color: "var(--accent-success)" }} title={`${gpu.name} — Driver ${gpu.driver_version}`}>
                <Zap size={13} style={{ verticalAlign: -2, marginRight: 3 }} />
                {t("llmEngine.gpuInfo", { name: gpu.name, vram: Math.round(gpu.vram_total_mb / 1024), free: Math.round(gpu.vram_free_mb / 1024) })}
              </span>
            )) : (
              <span style={{ color: "var(--text-muted)" }}>{t("llmEngine.noGPU")}</span>
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
          <Cpu size={14} /> {t("llmEngine.localTab")}
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
          <Globe size={14} /> {t("llmEngine.remoteTab")}
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
              <span style={styles.gpuTag}>{t("llmEngine.gpuTag")}</span>
            )}
          </div>
          <button
            className="btn-ghost"
            onClick={handleUnloadModel}
            style={{ marginTop: 8 }}
          >
            {t("llmEngine.unloadModel")}
          </button>
        </div>
      ) : (
        <div>
          {localLlmReady === false ? (
            <div style={{ padding: "10px 12px", marginBottom: 12, background: "rgba(244,67,54,0.08)", borderRadius: 6, border: "1px solid rgba(244,67,54,0.2)", fontSize: 12, color: "var(--accent-danger)", lineHeight: 1.6 }}>
              <strong>{t("llmEngine.disabledHint")}</strong>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                {t("llmEngine.disabledRequirements")}
              </div>
            </div>
          ) : (
            <p style={styles.hint}>
              {t("llmEngine.localHint")}
              <button
                className="btn-ghost btn-sm"
                onClick={() => openModelsDir().catch(logError("open-models-dir"))}
                style={{ marginLeft: 4, display: "inline-flex", alignItems: "center", gap: 4, verticalAlign: "middle", fontSize: 11, padding: "2px 6px" }}
                title={t("llmEngine.openModelsDirTitle")}
              >
                <FolderOpen size={12} /> {t("llmEngine.openModelsDir")}
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
                    {isActive && <span style={{ fontSize: 11, color: "var(--accent-primary)", fontWeight: 600, marginLeft: 8 }}>{t("llmEngine.active")}</span>}
                  </div>
                  {isActive ? (
                    <button
                      className="btn-ghost btn-sm"
                      onClick={handleUnloadModel}
                      disabled={llmLoading !== null}
                    >
                      {t("llmEngine.unload")}
                    </button>
                  ) : (
                  <button
                    className="btn-primary btn-sm"
                    onClick={() => handleLoadModel(m.path)}
                    disabled={llmLoading !== null || disabled}
                  >
                    {llmLoading === m.path ? t("llmEngine.loadingModel") : t("llmEngine.load")}
                  </button>
                  )}
                </div>
                );
              })}
            </div>
          ) : localLlmReady !== false ? (
            <p style={styles.hint}>
              {t("llmEngine.noModelsFound")}
            </p>
          ) : null}
          <button
            className="btn-ghost btn-sm"
            onClick={() => listModels().then(setModels)}
            style={{ marginTop: 8 }}
          >
            <RefreshCw size={12} /> {t("llmEngine.refreshModels")}
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
            {t("llmEngine.remoteHint")}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                {t("llmEngine.apiBaseUrl")}
              </label>
              <input
                type="text"
                value={remoteApiUrl}
                onChange={(e) => { setRemoteApiUrl(e.target.value); setRemoteStatus(""); }}
                placeholder={t("llmEngine.apiBaseUrlPlaceholder")}
                style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                {t("llmEngine.apiKey")}
              </label>
              <input
                type="password"
                value={remoteApiKey}
                onChange={(e) => { setRemoteApiKey(e.target.value); setRemoteStatus(""); }}
                placeholder={t("llmEngine.apiKeyPlaceholder")}
                style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
                {t("llmEngine.modelName")}
              </label>
              <input
                type="text"
                value={remoteModel}
                onChange={(e) => { setRemoteModel(e.target.value); setRemoteStatus(""); }}
                placeholder={t("llmEngine.modelNamePlaceholder")}
                style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border-color)", background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13 }}
              />
              <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                {t("llmEngine.modelExamples")}
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
                      setRemoteError(t("llmEngine.pleaseEnterApiKey"));
                      return;
                    }
                    await configureRemoteLLM(remoteApiUrl, keyToSend, remoteModel);
                    const status = await getLLMStatus();
                    setLLMStatus(status);
                    setRemoteStatus("ok");
                    setRemoteApiKey("••••••••"); // mask after save
                    setTimeout(() => setRemoteStatus(""), 3000);
                  } catch (e: unknown) {
                    setRemoteStatus("error");
                    setRemoteError(toErrorMessage(e) || t("llmEngine.configFailed"));
                  }
                }}
              >
                {remoteStatus === "saving" ? t("llmEngine.saving") : t("llmEngine.saveAndActivate")}
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
                      setRemoteError(result.error || t("llmEngine.testFailed"));
                    }
                  } catch (e: unknown) {
                    setRemoteStatus("error");
                    setRemoteError(toErrorMessage(e) || t("llmEngine.testFailedShort"));
                  }
                }}
              >
                <Zap size={12} /> {remoteStatus === "testing" ? t("llmEngine.testing") : t("llmEngine.testConnection")}
              </button>
              {llmStatus?.remote_api_url && (
                <button
                  className="btn-ghost btn-sm"
                  style={{ marginLeft: "auto", color: "var(--accent-danger)", padding: 4, lineHeight: 1 }}
                  title={t("llmEngine.removeConnection")}
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
                    } catch (e: unknown) {
                      setRemoteError(toErrorMessage(e) || "Failed to remove connection");
                    }
                  }}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>

            {remoteStatus === "ok" && (
              <p style={{ fontSize: 12, color: "var(--accent-success)", display: "flex", alignItems: "center", gap: 4 }}>
                ✓ {t("llmEngine.connected")}{remoteLatency != null && ` ${t("llmEngine.latency", { ms: remoteLatency })}`}
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
  );
}
