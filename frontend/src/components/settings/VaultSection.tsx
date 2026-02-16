/** Vault unlock form, vault stats, export/import backup functionality. */

import { useState, useCallback } from "react";
import { Lock, Unlock, Database, Download, Upload } from "lucide-react";
import { useVaultStore } from "../../store";
import { toErrorMessage } from "../../errorUtils";
import {
  unlockVault,
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
  const { vaultUnlocked, setVaultUnlocked } = useVaultStore();

  const [passphrase, setPassphrase] = useState("");
  const [vaultError, setVaultError] = useState("");
  const [exportPass, setExportPass] = useState("");
  const [exportStatus, setExportStatus] = useState("");
  const [importPass, setImportPass] = useState("");
  const [importStatus, setImportStatus] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const handleUnlockVault = useCallback(async () => {
    setVaultError("");
    try {
      await unlockVault(passphrase);
      setVaultUnlocked(true);
      setPassphrase("");
    } catch (e: unknown) {
      setVaultError(toErrorMessage(e) || "Failed to unlock vault");
    }
  }, [passphrase, setVaultUnlocked]);

  return (
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
                  } catch (e: unknown) {
                    setExportStatus(`Export failed: ${toErrorMessage(e)}`);
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
                    } catch (e: unknown) {
                      setImportStatus(`Import failed: ${toErrorMessage(e)}`);
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
  );
}
