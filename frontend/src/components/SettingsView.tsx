/** Settings panel — tabbed layout: Detection, AI Engine, General. */

import { useState, useEffect } from "react";
import { useVaultStore, useDetectionStore, useConnectionStore } from "../store";
import {
  getVaultStatus,
  getVaultStats,
  getLLMStatus,
  getSettings,
  updateSettings,
  logError,
} from "../api";
import type { VaultStats } from "../types";
import { styles } from "./settings/settingsStyles";
import VaultSection from "./settings/VaultSection";
import DetectionSection from "./settings/DetectionSection";
import LLMEngineSection from "./settings/LLMEngineSection";
import LicenseSection from "./settings/LicenseSection";
import UpdatesSection from "./settings/UpdatesSection";

const TABS = [
  { id: "detection", label: "Detection", icon: "🔍" },
  { id: "ai",        label: "AI Engine", icon: "🧠" },
  { id: "vault",     label: "Vault",     icon: "🔒" },
  { id: "updates",   label: "Updates",   icon: "🚀" },
  { id: "general",   label: "License",   icon: "⚙️" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function SettingsView() {
  const { vaultUnlocked, setVaultUnlocked } = useVaultStore();
  const { setLLMStatus, setDetectionSettings } = useDetectionStore();
  const { backendReady } = useConnectionStore();

  const [vaultStats, setVaultStats] = useState<VaultStats | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("detection");

  // Load initial status
  useEffect(() => {
    if (!backendReady) return;
    getVaultStatus().then((s) => setVaultUnlocked(s.unlocked)).catch(logError("vault-status"));
    Promise.all([getSettings(), getLLMStatus()])
      .then(([s, status]) => {
        setLLMStatus(status);
        const hasValidLlm =
          status.loaded ||
          (status.provider === "remote" && !!status.remote_api_url && !!status.remote_model);
        const llmEnabled = (s.llm_detection_enabled as boolean) && hasValidLlm;
        setDetectionSettings({
          regex_enabled: s.regex_enabled as boolean,
          custom_patterns_enabled: (s.custom_patterns_enabled as boolean) ?? true,
          ner_enabled: s.ner_enabled as boolean,
          llm_detection_enabled: llmEnabled,
          ner_backend: s.ner_backend as string,
          detection_fuzziness: (s.detection_fuzziness as number) ?? 0.5,
          detection_language: (s.detection_language as string) ?? "auto",
        });
        if (s.llm_detection_enabled && !hasValidLlm) {
          updateSettings({ llm_detection_enabled: false }).catch(logError("update-settings"));
        }
      })
      .catch(logError("load-settings"));
  }, [backendReady, setVaultUnlocked, setLLMStatus, setDetectionSettings]);

  useEffect(() => {
    if (vaultUnlocked) {
      getVaultStats().then(setVaultStats).catch(logError("vault-stats"));
    }
  }, [vaultUnlocked]);

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>Settings</h2>

      {/* ── Tab bar ── */}
      <div
        style={{
          display: "flex",
          gap: 0,
          marginBottom: 20,
          borderBottom: "1px solid var(--border-color)",
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 18px",
                fontSize: 13,
                fontWeight: active ? 600 : 400,
                color: active ? "var(--text-primary)" : "var(--text-muted)",
                background: "transparent",
                border: "none",
                borderBottom: active
                  ? "2px solid var(--accent-primary)"
                  : "2px solid transparent",
                borderRadius: 0,
                cursor: "pointer",
                transition: "color 0.15s, border-color 0.15s",
                marginBottom: -1,
              }}
              onMouseEnter={(e) => {
                if (!active) (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
              }}
              onMouseLeave={(e) => {
                if (!active) (e.currentTarget as HTMLElement).style.color = "var(--text-muted)";
              }}
            >
              <span style={{ fontSize: 15 }}>{tab.icon}</span>
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Tab content ── */}
      {activeTab === "detection" && <DetectionSection />}
      {activeTab === "ai" && <LLMEngineSection />}
      {activeTab === "vault" && <VaultSection vaultStats={vaultStats} setVaultStats={setVaultStats} />}
      {activeTab === "updates" && <UpdatesSection />}
      {activeTab === "general" && <LicenseSection />}
    </div>
  );
}
