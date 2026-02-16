/** Revalidation dialog — prompts the user to revalidate their license online.
 *
 * Shown when the stored license is nearing expiry (< 7 days) or has expired.
 * No Firebase — just triggers online revalidation using machine fingerprint.
 */

import { useState, useCallback } from "react";
import { useSnackbarStore, useLicenseStore } from "../store";
import { toErrorMessage } from "../errorUtils";
import { revalidateLicense } from "../licenseApi";

interface Props {
  daysRemaining: number | null;
  onDismiss: () => void;
}

export default function RevalidationDialog({ daysRemaining, onDismiss }: Props) {
  const { addSnackbar } = useSnackbarStore();
  const { setLicenseStatus } = useLicenseStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const expired = daysRemaining !== null && daysRemaining <= 0;

  const handleRevalidate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await revalidateLicense();
      if (status.valid) {
        setLicenseStatus(status);
        addSnackbar("License revalidated successfully!", "success");
        onDismiss();
      } else {
        setError(status.error ?? "Revalidation failed");
      }
    } catch (e: unknown) {
      setError(toErrorMessage(e) ?? "Revalidation failed. Check your internet connection.");
    } finally {
      setLoading(false);
    }
  }, [setLicenseStatus, addSnackbar, onDismiss]);

  return (
    <div role="dialog" aria-modal="true" aria-label="License revalidation" style={styles.overlay}>
      <div style={styles.dialog}>
        <h2 style={styles.title}>
          {expired ? "License Expired" : "License Renewal Required"}
        </h2>
        <p style={styles.message}>
          {expired
            ? "Your license has expired. Please revalidate online or paste a new license key to continue using promptShield."
            : `Your license expires in ${daysRemaining} day${daysRemaining === 1 ? "" : "s"}. Please revalidate online to avoid interruption.`}
        </p>

        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.actions}>
          <button
            onClick={handleRevalidate}
            disabled={loading}
            style={{ ...styles.button, ...styles.buttonPrimary }}
          >
            {loading ? "Revalidating..." : "Revalidate Now"}
          </button>
          {!expired && (
            <button onClick={onDismiss} style={styles.button}>
              Remind Me Later
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(0,0,0,0.6)",
    zIndex: 9999,
  },
  dialog: {
    width: "100%",
    maxWidth: 400,
    background: "var(--bg-secondary, #161b22)",
    border: "1px solid var(--border-color, #30363d)",
    borderRadius: 12,
    padding: 24,
    boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
  },
  title: {
    fontSize: 18,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
    margin: "0 0 8px 0",
  },
  message: {
    fontSize: 13,
    color: "var(--text-secondary, #8b949e)",
    margin: "0 0 16px 0",
    lineHeight: 1.5,
  },
  error: {
    background: "rgba(248,81,73,0.1)",
    border: "1px solid rgba(248,81,73,0.4)",
    borderRadius: 6,
    padding: "8px 12px",
    color: "#f85149",
    fontSize: 13,
    marginBottom: 12,
  },
  actions: {
    display: "flex",
    gap: 8,
    justifyContent: "flex-end",
  },
  button: {
    padding: "8px 16px",
    borderRadius: 6,
    border: "1px solid var(--border-color, #30363d)",
    background: "transparent",
    color: "var(--text-primary, #c9d1d9)",
    fontSize: 13,
    cursor: "pointer",
  },
  buttonPrimary: {
    background: "var(--accent-primary, #238636)",
    border: "none",
    color: "#fff",
    fontWeight: 600,
  },
};
