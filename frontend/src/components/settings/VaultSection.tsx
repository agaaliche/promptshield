/** Vault stats, export/import backup functionality. */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Unlock, Download, Upload } from "../../icons";
import { toErrorMessage } from "../../errorUtils";
import {
  getVaultStats,
  exportVault,
  importVault,
  logError,
} from "../../api";
import type { VaultStats } from "../../types";
import { Section, StatItem, styles } from "./settingsStyles";

export interface VaultSectionProps {
  vaultStats: VaultStats | null;
  setVaultStats: (s: VaultStats | null) => void;
}

export default function VaultSection({ vaultStats, setVaultStats }: VaultSectionProps) {
  const { t } = useTranslation();

  const [exportStatus, setExportStatus] = useState("");
  const [importStatus, setImportStatus] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [exportIsError, setExportIsError] = useState(false);
  const [importIsError, setImportIsError] = useState(false);

  return (
    <Section>
      <div style={styles.vaultInfo}>
        <div style={styles.badge}>
          <Unlock size={14} style={{ color: "var(--accent-success)" }} />
          <span style={{ color: "var(--accent-success)" }}>{t("vault.unlocked")}</span>
        </div>
        {vaultStats && (
          <div style={styles.statsGrid}>
            <StatItem label={t("vault.tokensStored")} value={vaultStats.total_tokens} />
            <StatItem label={t("vault.documents")} value={vaultStats.total_documents} />
            <StatItem
              label={t("vault.vaultSize")}
              value={`${(vaultStats.vault_size_bytes / 1024).toFixed(1)} ${t("vault.kb")}`}
            />
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <p style={{ ...styles.hint, marginBottom: 8 }}>{t("vault.exportHint")}</p>
          <div style={styles.formRow}>
            <button
              className="btn-ghost btn-sm"
              onClick={async () => {
                try {
                  setExportStatus("");
                  const data = await exportVault();
                  const blob = new Blob([data], { type: "application/json" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `vault-export-${Date.now()}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  setExportStatus(t("vault.exportedSuccessfully"));
                  setExportIsError(false);
                } catch (e: unknown) {
                  setExportStatus(t("vault.exportFailed", { error: toErrorMessage(e) }));
                  setExportIsError(true);
                }
              }}
            >
              <Download size={12} /> {t("vault.exportVault")}
            </button>
          </div>
          {exportStatus && (
            <p style={{ fontSize: 12, marginTop: 4, color: exportIsError ? "var(--accent-danger)" : "var(--accent-success)" }}>
              {exportStatus}
            </p>
          )}
        </div>

        {/* ── Import ── */}
        <div style={{ marginTop: 16, borderTop: "1px solid var(--border-color)", paddingTop: 12 }}>
          <p style={{ ...styles.hint, marginBottom: 8 }}>{t("vault.importHint")}</p>
          <div style={styles.formRow}>
            <label
              className="btn-ghost btn-sm"
              style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}
            >
              <Upload size={12} />
              {importFile ? importFile.name : t("vault.chooseFile")}
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
              <button
                className="btn-ghost btn-sm"
                disabled={isImporting}
                onClick={async () => {
                  try {
                    setImportStatus("");
                    setIsImporting(true);
                    const text = await importFile.text();
                    const result = await importVault(text);
                    setImportStatus(
                      t("vault.importResult", { imported: result.imported, skipped: result.skipped ?? 0, errors: result.errors ?? 0 })
                    );
                    setImportIsError(false);
                    setImportFile(null);
                    // Refresh vault stats
                    getVaultStats().then(setVaultStats).catch(logError("vault-stats"));
                  } catch (e: unknown) {
                    setImportStatus(t("vault.importFailed", { error: toErrorMessage(e) }));
                    setImportIsError(true);
                  } finally {
                    setIsImporting(false);
                  }
                }}
              >
                {isImporting ? t("vault.importing") : t("vault.restoreBackup")}
              </button>
            </div>
          )}
          {importStatus && (
            <p style={{ fontSize: 12, marginTop: 4, color: importIsError ? "var(--accent-danger)" : "var(--accent-success)" }}>
              {importStatus}
            </p>
          )}
        </div>
      </div>
    </Section>
  );
}
