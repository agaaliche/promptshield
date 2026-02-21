/** Settings panel — tabbed layout: Detection, AI Engine, General. */

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useDetectionStore, useConnectionStore } from "../store";
import {
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
import AccountSection from "./settings/AccountSection";
import UpdatesSection from "./settings/UpdatesSection";
import { ScanSearch, Brain, Lock, ArrowUpCircle, User } from "../icons";

const TAB_IDS = ["detection", "ai", "vault", "updates", "general"] as const;

type TabId = (typeof TAB_IDS)[number];

export default function SettingsView() {
  const { t } = useTranslation();
  const { setLLMStatus, setDetectionSettings } = useDetectionStore();
  const { backendReady } = useConnectionStore();

  const [vaultStats, setVaultStats] = useState<VaultStats | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("detection");

  // Load initial status
  useEffect(() => {
    if (!backendReady) return;
    getVaultStats().then(setVaultStats).catch(logError("vault-stats"));
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
  }, [backendReady, setLLMStatus, setDetectionSettings]);

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>{t("settingsView.title")}</h2>

      {/* ── Tab bar ── */}
      <div
        style={{
          display: "flex",
          gap: 0,
          marginBottom: 20,
          borderBottom: "1px solid var(--border-color)",
        }}
      >
        {(["detection", "ai", "vault", "updates", "general"] as const).map((id) => {
          const active = activeTab === id;
          const labels: Record<TabId, { icon: React.ReactNode; label: string }> = {
            detection: { icon: <ScanSearch size={15} />, label: t("settingsView.tabDetection") },
            ai:        { icon: <Brain size={15} />, label: t("settingsView.tabAIEngine") },
            vault:     { icon: <Lock size={15} />, label: t("settingsView.tabVault") },
            updates:   { icon: <ArrowUpCircle size={15} />, label: t("settingsView.tabUpdates") },
            general:   { icon: <User size={15} />, label: t("settingsView.tabAccount") },
          };
          const tab = labels[id];
          return (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
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
              {tab.icon}
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
      {activeTab === "general" && <AccountSection />}
    </div>
  );
}
