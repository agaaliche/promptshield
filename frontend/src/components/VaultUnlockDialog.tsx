/** Vault unlock prompt overlay — used before tokenization. */

import { Lock } from "lucide-react";
import type { CSSProperties } from "react";
import { Z_MODAL } from "../zIndex";

interface VaultUnlockDialogProps {
  vaultPass: string;
  vaultError: string;
  isProcessing: boolean;
  onPassChange: (pass: string) => void;
  onUnlock: () => void;
  onCancel: () => void;
}

export default function VaultUnlockDialog({
  vaultPass,
  vaultError,
  isProcessing,
  onPassChange,
  onUnlock,
  onCancel,
}: VaultUnlockDialogProps) {
  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-labelledby="vault-unlock-title">
      <div style={dialogStyle}>
        <Lock size={24} style={{ color: "var(--accent-warning)", marginBottom: 8 }} />
        <h3 id="vault-unlock-title" style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>Unlock Vault</h3>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
          Tokenization requires the vault to store reversible mappings.
          Enter your passphrase to unlock or create the vault.
        </p>
        <div style={{ display: "flex", gap: 8, width: "100%" }}>
          <input
            type="password"
            value={vaultPass}
            onChange={(e) => onPassChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onUnlock()}
            placeholder="Vault passphrase"
            autoFocus
            style={{ flex: 1 }}
          />
          <button
            className="btn-primary"
            onClick={onUnlock}
            disabled={!vaultPass || isProcessing}
          >
            Unlock & Anonymize
          </button>
        </div>
        {vaultError && (
          <p style={{ color: "var(--accent-danger)", fontSize: 12, marginTop: 6 }}>{vaultError}</p>
        )}
        <button
          className="btn-ghost btn-sm"
          style={{ marginTop: 8 }}
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

const overlayStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: Z_MODAL,
};

const dialogStyle: CSSProperties = {
  background: "var(--bg-secondary)",
  borderRadius: 12,
  padding: 24,
  maxWidth: 420,
  width: "90%",
  textAlign: "center",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
};
