/** Key-paste screen — shown when no valid local license key is found.
 *
 * The desktop app is purely key-based: users get their license key from
 * promptshield.ca and paste it here. No login / email / password / social
 * sign-in in the app itself.
 */

import { useState, useCallback } from "react";
import { useAppStore } from "../store";
import { storeLocalLicense } from "../licenseApi";
import type { LicenseStatus } from "../types";

export default function AuthScreen() {
  const { setLicenseStatus, setLicenseChecked, addSnackbar } = useAppStore();
  const [licenseKey, setLicenseKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActivate = useCallback(async () => {
    const trimmed = licenseKey.trim();
    if (!trimmed) {
      setError("Please paste your license key");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const status: LicenseStatus = await storeLocalLicense(trimmed);
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("License activated!", "success");
      } else {
        setError(status.error ?? "Invalid or expired license key");
      }
    } catch (e: any) {
      setError(e.message ?? "Failed to apply license key");
    } finally {
      setLoading(false);
    }
  }, [licenseKey, setLicenseStatus, setLicenseChecked, addSnackbar]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleActivate();
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <h1 style={styles.title}>promptShield</h1>
          <p style={styles.subtitle}>Secure Document Anonymization</p>
        </div>

        <div style={styles.iconContainer}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--accent-primary, #58a6ff)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>

        <p style={styles.description}>
          Enter your license key to get started. You can obtain a key from your
          account dashboard at{" "}
          <a
            href="https://promptshield.ca"
            target="_blank"
            rel="noopener noreferrer"
            style={styles.link}
          >
            promptshield.ca
          </a>
          .
        </p>

        {error && <div style={styles.error}>{error}</div>}

        <form onSubmit={handleSubmit} style={styles.form}>
          <label style={styles.label}>License Key</label>
          <textarea
            value={licenseKey}
            onChange={(e) => setLicenseKey(e.target.value)}
            placeholder="Paste your license key here..."
            rows={5}
            style={styles.textarea}
            autoFocus
            spellCheck={false}
          />

          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.button,
              ...(loading ? styles.buttonDisabled : {}),
            }}
          >
            {loading ? "Activating..." : "Activate License"}
          </button>
        </form>

        <div style={styles.footer}>
          <p style={styles.footerText}>
            Don't have a key?{" "}
            <a
              href="https://promptshield.ca"
              target="_blank"
              rel="noopener noreferrer"
              style={styles.link}
            >
              Sign up at promptshield.ca
            </a>
          </p>
          <p style={styles.footerHint}>
            Your license works offline for up to 30 days between validations.
          </p>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100vh",
    width: "100vw",
    background: "var(--bg-primary, #0d1117)",
    padding: 24,
  },
  card: {
    width: "100%",
    maxWidth: 440,
    background: "var(--bg-secondary, #161b22)",
    borderRadius: 12,
    border: "1px solid var(--border-color, #30363d)",
    padding: 32,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
  header: {
    textAlign: "center" as const,
    marginBottom: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    color: "var(--accent-primary, #58a6ff)",
    margin: 0,
    letterSpacing: "-0.5px",
  },
  subtitle: {
    fontSize: 13,
    color: "var(--text-secondary, #8b949e)",
    margin: "4px 0 0 0",
  },
  iconContainer: {
    display: "flex",
    justifyContent: "center",
    marginBottom: 16,
  },
  description: {
    fontSize: 13,
    color: "var(--text-secondary, #8b949e)",
    lineHeight: 1.5,
    textAlign: "center" as const,
    marginBottom: 20,
  },
  error: {
    background: "rgba(248,81,73,0.1)",
    border: "1px solid rgba(248,81,73,0.4)",
    borderRadius: 6,
    padding: "8px 12px",
    color: "#f85149",
    fontSize: 13,
    marginBottom: 16,
  },
  form: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-secondary, #8b949e)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
  },
  textarea: {
    padding: "10px 12px",
    borderRadius: 6,
    border: "1px solid var(--border-color, #30363d)",
    background: "var(--bg-primary, #0d1117)",
    color: "var(--text-primary, #c9d1d9)",
    fontSize: 12,
    fontFamily: "monospace",
    resize: "vertical" as const,
    outline: "none",
    marginBottom: 4,
  },
  button: {
    marginTop: 8,
    padding: "12px 0",
    borderRadius: 6,
    border: "none",
    background: "var(--accent-primary, #238636)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    transition: "opacity 0.15s",
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
  },
  link: {
    color: "var(--accent-primary, #58a6ff)",
    textDecoration: "none",
  },
  footer: {
    marginTop: 24,
    textAlign: "center" as const,
  },
  footerText: {
    fontSize: 13,
    color: "var(--text-secondary, #8b949e)",
    margin: "4px 0",
  },
  footerHint: {
    fontSize: 11,
    color: "var(--text-muted, #6e7681)",
    margin: "8px 0 0 0",
  },
};
