/** Settings panel — vault, LLM, detection, and app settings. */

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

export default function SettingsView() {
  const { vaultUnlocked, setVaultUnlocked } = useVaultStore();
  const { setLLMStatus, detectionSettings, setDetectionSettings } = useDetectionStore();
  const { backendReady } = useConnectionStore();

  const [vaultStats, setVaultStats] = useState<VaultStats | null>(null);

  // Load initial status
  useEffect(() => {
    if (!backendReady) return;
    getVaultStatus().then((s) => setVaultUnlocked(s.unlocked)).catch(logError("vault-status"));
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
      <VaultSection vaultStats={vaultStats} setVaultStats={setVaultStats} />
      <DetectionSection />
      {detectionSettings.llm_detection_enabled && <LLMEngineSection />}
      <LicenseSection />
    </div>
  );
}
