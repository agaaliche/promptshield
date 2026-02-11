/** Authentication screen — shown before the main app when no valid license. */

import { useState, useCallback } from "react";
import { useAppStore } from "../store";
import {
  register,
  login,
  getMe,
  fullActivation,
  storeLocalLicense,
  validateLocalLicense,
} from "../licenseApi";
import type { LicenseStatus } from "../types";

type AuthMode = "login" | "register" | "offline-key";

export default function AuthScreen() {
  const { setLicenseStatus, setLicenseChecked, addSnackbar } = useAppStore();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [offlineKey, setOfflineKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      await getMe();
      const status = await fullActivation();
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("License activated successfully!", "success");
      } else {
        setError(status.error ?? "Activation failed");
      }
    } catch (e: any) {
      setError(e.message ?? "Login failed");
    } finally {
      setLoading(false);
    }
  }, [email, password, setLicenseStatus, setLicenseChecked, addSnackbar]);

  const handleRegister = useCallback(async () => {
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await register(email, password);
      // Auto-login after registration
      await login(email, password);
      await getMe();
      const status = await fullActivation();
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("Account created and license activated!", "success");
      } else {
        setError(status.error ?? "Activation failed after registration");
      }
    } catch (e: any) {
      setError(e.message ?? "Registration failed");
    } finally {
      setLoading(false);
    }
  }, [email, password, confirmPassword, setLicenseStatus, setLicenseChecked, addSnackbar]);

  const handleOfflineKey = useCallback(async () => {
    const trimmed = offlineKey.trim();
    if (!trimmed) {
      setError("Please paste your offline license key");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const status: LicenseStatus = await storeLocalLicense(trimmed);
      if (status.valid) {
        setLicenseStatus(status);
        setLicenseChecked(true);
        addSnackbar("Offline license activated!", "success");
      } else {
        setError(status.error ?? "Invalid license key");
      }
    } catch (e: any) {
      setError(e.message ?? "Failed to apply offline key");
    } finally {
      setLoading(false);
    }
  }, [offlineKey, setLicenseStatus, setLicenseChecked, addSnackbar]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "login") handleLogin();
    else if (mode === "register") handleRegister();
    else handleOfflineKey();
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        {/* Logo / Title */}
        <div style={styles.header}>
          <h1 style={styles.title}>promptShield</h1>
          <p style={styles.subtitle}>Secure Document Anonymization</p>
        </div>

        {/* Tabs */}
        <div style={styles.tabs}>
          <button
            style={{ ...styles.tab, ...(mode === "login" ? styles.tabActive : {}) }}
            onClick={() => { setMode("login"); setError(null); }}
          >
            Sign In
          </button>
          <button
            style={{ ...styles.tab, ...(mode === "register" ? styles.tabActive : {}) }}
            onClick={() => { setMode("register"); setError(null); }}
          >
            Create Account
          </button>
          <button
            style={{ ...styles.tab, ...(mode === "offline-key" ? styles.tabActive : {}) }}
            onClick={() => { setMode("offline-key"); setError(null); }}
          >
            Offline Key
          </button>
        </div>

        {/* Error */}
        {error && <div style={styles.error}>{error}</div>}

        {/* Form */}
        <form onSubmit={handleSubmit} style={styles.form}>
          {mode !== "offline-key" && (
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

              {mode === "register" && (
                <>
                  <label style={styles.label}>Confirm Password</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    minLength={8}
                    style={styles.input}
                  />
                </>
              )}
            </>
          )}

          {mode === "offline-key" && (
            <>
              <label style={styles.label}>License Key</label>
              <textarea
                value={offlineKey}
                onChange={(e) => setOfflineKey(e.target.value)}
                placeholder="Paste your offline license key here..."
                rows={5}
                style={{ ...styles.input, resize: "vertical", fontFamily: "monospace", fontSize: 12 }}
                autoFocus
              />
              <p style={styles.hint}>
                Get your offline key from{" "}
                <a
                  href="https://app.promptshield.com/license"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={styles.link}
                >
                  app.promptshield.com/license
                </a>
              </p>
            </>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{ ...styles.button, ...(loading ? styles.buttonDisabled : {}) }}
          >
            {loading
              ? "Please wait..."
              : mode === "login"
                ? "Sign In & Activate"
                : mode === "register"
                  ? "Create Account & Activate"
                  : "Apply License Key"}
          </button>
        </form>

        {/* Footer */}
        <div style={styles.footer}>
          <p style={styles.footerText}>
            {mode === "login" ? (
              <>
                Don't have an account?{" "}
                <button style={styles.linkButton} onClick={() => setMode("register")}>
                  Create one
                </button>
              </>
            ) : mode === "register" ? (
              <>
                Already have an account?{" "}
                <button style={styles.linkButton} onClick={() => setMode("login")}>
                  Sign in
                </button>
              </>
            ) : (
              <>
                Have an account?{" "}
                <button style={styles.linkButton} onClick={() => setMode("login")}>
                  Sign in online
                </button>
              </>
            )}
          </p>
          <p style={styles.footerText}>
            No internet?{" "}
            <button style={styles.linkButton} onClick={() => setMode("offline-key")}>
              Use an offline key
            </button>
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
    maxWidth: 420,
    background: "var(--bg-secondary, #161b22)",
    borderRadius: 12,
    border: "1px solid var(--border-color, #30363d)",
    padding: 32,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
  },
  header: {
    textAlign: "center" as const,
    marginBottom: 24,
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
  button: {
    marginTop: 12,
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
  hint: {
    fontSize: 12,
    color: "var(--text-muted, #6e7681)",
    margin: 0,
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
  linkButton: {
    background: "none",
    border: "none",
    color: "var(--accent-primary, #58a6ff)",
    cursor: "pointer",
    padding: 0,
    fontSize: 13,
    textDecoration: "underline",
  },
};
