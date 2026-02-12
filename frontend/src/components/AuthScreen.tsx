/** Activation screen — shown when no valid local license key is found.
 *
 * Two tabs:
 *   1. "Sign In" (default) — email/password or Google → authenticates online
 *      via Firebase Auth SDK → activates license automatically.
 *   2. "License Key" — paste an offline license key for air-gapped setups.
 *
 * After first activation the user can disable online mode in Settings.
 */

import { useState, useCallback } from "react";
import { useAppStore } from "../store";
import {
  storeLocalLicense,
  signInOnline,
  signInWithGoogle,
} from "../licenseApi";
import type { LicenseStatus } from "../types";

type Mode = "signin" | "key";

export default function AuthScreen() {
  const { setLicenseStatus, setLicenseChecked, addSnackbar } = useAppStore();

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [licenseKey, setLicenseKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Online sign-in ──────────────────────────────────────────
  const handleSignIn = useCallback(async () => {
    if (!email.trim()) { setError("Please enter your email"); return; }
    if (!password) { setError("Please enter your password"); return; }
    setLoading(true);
    setError(null);
    try {
      const status: LicenseStatus = await signInOnline(email.trim(), password);
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("License activated!", "success");
      } else {
        setError(status.error ?? "Activation failed");
      }
    } catch (e: any) {
      setError(e.message ?? "Sign-in failed");
    } finally {
      setLoading(false);
    }
  }, [email, password, setLicenseStatus, setLicenseChecked, addSnackbar]);

  // ── Google sign-in ──────────────────────────────────────────
  const handleGoogle = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status: LicenseStatus = await signInWithGoogle();
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("License activated!", "success");
      } else {
        setError(status.error ?? "Activation failed");
      }
    } catch (e: any) {
      if (e.message !== "Sign-in cancelled") {
        setError(e.message ?? "Google sign-in failed");
      }
    } finally {
      setLoading(false);
    }
  }, [setLicenseStatus, setLicenseChecked, addSnackbar]);

  // ── Offline key paste ───────────────────────────────────────
  const handleActivateKey = useCallback(async () => {
    const trimmed = licenseKey.trim();
    if (!trimmed) { setError("Please paste your license key"); return; }
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
    if (mode === "signin") handleSignIn();
    else handleActivateKey();
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <h1 style={styles.title}>promptShield</h1>
          <p style={styles.subtitle}>Secure Document Anonymization</p>
        </div>

        {/* ── Tab bar ── */}
        <div style={styles.tabs}>
          <button
            style={{ ...styles.tab, ...(mode === "signin" ? styles.tabActive : {}) }}
            onClick={() => { setMode("signin"); setError(null); }}
          >
            Sign In
          </button>
          <button
            style={{ ...styles.tab, ...(mode === "key" ? styles.tabActive : {}) }}
            onClick={() => { setMode("key"); setError(null); }}
          >
            License Key
          </button>
        </div>

        {error && <div style={styles.error}>{error}</div>}

        {mode === "signin" && (
          <div style={styles.socialContainer}>
            <button
              type="button"
              disabled={loading}
              style={styles.socialButton}
              onClick={handleGoogle}
            >
              <svg width="18" height="18" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
                <path fill="#34A853" d="M10.53 28.59A14.5 14.5 0 019.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.97 23.97 0 000 24c0 3.77.9 7.35 2.56 10.56l7.97-5.97z" />
                <path fill="#FBBC05" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.97C6.51 42.62 14.62 48 24 48z" />
              </svg>
              <span>Sign in with Google</span>
            </button>
            <div style={styles.divider}>
              <span style={styles.dividerLine} />
              <span style={styles.dividerText}>or</span>
              <span style={styles.dividerLine} />
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} style={styles.form}>
          {mode === "signin" ? (
            <>
              <label style={styles.label}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
                style={styles.input}
                autoFocus
              />
              <label style={styles.label}>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                minLength={8}
                style={styles.input}
              />
            </>
          ) : (
            <>
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
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              ...styles.button,
              ...(loading ? styles.buttonDisabled : {}),
            }}
          >
            {loading
              ? "Please wait..."
              : mode === "signin"
                ? "Sign In & Activate"
                : "Activate License"}
          </button>
        </form>

        <div style={styles.footer}>
          <p style={styles.footerText}>
            Don't have an account?{" "}
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
            {mode === "signin"
              ? "After activation, the app works offline for up to 30 days."
              : "No internet? Paste an offline license key from your account dashboard."}
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
    marginBottom: 20,
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
  tabs: {
    display: "flex",
    gap: 0,
    marginBottom: 20,
    borderBottom: "1px solid var(--border-color, #30363d)",
  },
  tab: {
    flex: 1,
    padding: "8px 0",
    background: "none",
    border: "none",
    borderBottom: "2px solid transparent",
    color: "var(--text-secondary, #8b949e)",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.15s",
  },
  tabActive: {
    color: "var(--accent-primary, #58a6ff)",
    borderBottomColor: "var(--accent-primary, #58a6ff)",
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
  socialContainer: {
    display: "flex",
    flexDirection: "column" as const,
    gap: 8,
    marginBottom: 16,
  },
  socialButton: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: "10px 0",
    borderRadius: 6,
    border: "1px solid var(--border-color, #30363d)",
    background: "var(--bg-primary, #0d1117)",
    color: "var(--text-primary, #c9d1d9)",
    fontSize: 14,
    cursor: "pointer",
    transition: "border-color 0.15s, background 0.15s",
  },
  divider: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    margin: "4px 0",
  },
  dividerLine: {
    flex: 1,
    height: 1,
    background: "var(--border-color, #30363d)",
  },
  dividerText: {
    fontSize: 12,
    color: "var(--text-muted, #6e7681)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.5px",
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
  input: {
    padding: "10px 12px",
    borderRadius: 6,
    border: "1px solid var(--border-color, #30363d)",
    background: "var(--bg-primary, #0d1117)",
    color: "var(--text-primary, #c9d1d9)",
    fontSize: 14,
    outline: "none",
    marginBottom: 4,
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
    marginTop: 20,
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
