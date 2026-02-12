/** Authentication screen — Firebase Auth with email/password + social sign-in. */

import { useState, useCallback } from "react";
import {
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
} from "firebase/auth";
import { auth, googleProvider, microsoftProvider } from "../firebaseConfig";
import { useAppStore } from "../store";
import {
  syncFirebaseUser,
  isTauri,
  fullActivation,
  storeLocalLicense,
  getLicenseStatus,
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

  /** After Firebase auth succeeds, sync user with licensing server + activate. */
  const activateAfterAuth = useCallback(
    async (successMsg: string) => {
      await syncFirebaseUser();

      if (isTauri()) {
        const status = await fullActivation();
        if (status.valid) {
          setLicenseStatus(status);
          setLicenseChecked(true);
          addSnackbar(successMsg, "success");
        } else {
          setError(status.error ?? "Activation failed");
        }
      } else {
        const ls = await getLicenseStatus();
        const user = auth.currentUser;
        const webStatus: LicenseStatus = {
          valid: ls.valid,
          payload: ls.plan
            ? { plan: ls.plan, email: user?.email ?? "", seats: ls.seats ?? 1, machine_id: "web", issued: "", expires: ls.expires_at ?? "", v: 1 }
            : null,
          error: ls.valid ? null : (ls.message ?? "No active license"),
          days_remaining: ls.days_remaining ?? null,
        };
        setLicenseStatus(webStatus);
        setLicenseChecked(true);
        if (webStatus.valid) {
          addSnackbar(successMsg, "success");
        } else {
          setError(webStatus.error ?? "No active license");
        }
      }
    },
    [setLicenseStatus, setLicenseChecked, addSnackbar],
  );

  const handleLogin = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await signInWithEmailAndPassword(auth, email, password);
      await activateAfterAuth("Signed in successfully!");
    } catch (e: any) {
      setError(friendlyError(e.code));
    } finally {
      setLoading(false);
    }
  }, [email, password, activateAfterAuth]);

  const handleRegister = useCallback(async () => {
    if (password !== confirmPassword) { setError("Passwords do not match"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    setLoading(true);
    setError(null);
    try {
      await createUserWithEmailAndPassword(auth, email, password);
      await activateAfterAuth("Account created!");
    } catch (e: any) {
      setError(friendlyError(e.code));
    } finally {
      setLoading(false);
    }
  }, [email, password, confirmPassword, activateAfterAuth]);

  const handleSocial = useCallback(
    async (provider: "google" | "microsoft") => {
      setLoading(true);
      setError(null);
      try {
        const p = provider === "google" ? googleProvider : microsoftProvider;
        await signInWithPopup(auth, p);
        await activateAfterAuth("Signed in successfully!");
      } catch (e: any) {
        if (e.code !== "auth/popup-closed-by-user") {
          setError(friendlyError(e.code));
        }
      } finally {
        setLoading(false);
      }
    },
    [activateAfterAuth],
  );

  const handleOfflineKey = useCallback(async () => {
    const trimmed = offlineKey.trim();
    if (!trimmed) { setError("Please paste your offline license key"); return; }
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
        <div style={styles.header}>
          <h1 style={styles.title}>promptShield</h1>
          <p style={styles.subtitle}>Secure Document Anonymization</p>
        </div>

        <div style={styles.tabs}>
          <button style={{ ...styles.tab, ...(mode === "login" ? styles.tabActive : {}) }} onClick={() => { setMode("login"); setError(null); }}>Sign In</button>
          <button style={{ ...styles.tab, ...(mode === "register" ? styles.tabActive : {}) }} onClick={() => { setMode("register"); setError(null); }}>Create Account</button>
          <button style={{ ...styles.tab, ...(mode === "offline-key" ? styles.tabActive : {}) }} onClick={() => { setMode("offline-key"); setError(null); }}>Offline Key</button>
        </div>

        {error && <div style={styles.error}>{error}</div>}

        {mode !== "offline-key" && (
          <div style={styles.socialContainer}>
            <button type="button" disabled={loading} style={styles.socialButton} onClick={() => handleSocial("google")}>
              <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#34A853" d="M10.53 28.59A14.5 14.5 0 019.5 24c0-1.59.28-3.14.76-4.59l-7.98-6.19A23.97 23.97 0 000 24c0 3.77.9 7.35 2.56 10.56l7.97-5.97z"/><path fill="#FBBC05" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 5.97C6.51 42.62 14.62 48 24 48z"/></svg>
              <span>Continue with Google</span>
            </button>
            <button type="button" disabled={loading} style={styles.socialButton} onClick={() => handleSocial("microsoft")}>
              <svg width="18" height="18" viewBox="0 0 21 21"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>
              <span>Continue with Microsoft</span>
            </button>
            <div style={styles.divider}><span style={styles.dividerLine} /><span style={styles.dividerText}>or</span><span style={styles.dividerLine} /></div>
          </div>
        )}

        <form onSubmit={handleSubmit} style={styles.form}>
          {mode !== "offline-key" && (
            <>
              <label style={styles.label}>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com" required style={styles.input} autoFocus />
              <label style={styles.label}>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required minLength={8} style={styles.input} />
              {mode === "register" && (
                <>
                  <label style={styles.label}>Confirm Password</label>
                  <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="••••••••" required minLength={8} style={styles.input} />
                </>
              )}
            </>
          )}

          {mode === "offline-key" && (
            <>
              <label style={styles.label}>License Key</label>
              <textarea value={offlineKey} onChange={(e) => setOfflineKey(e.target.value)} placeholder="Paste your offline license key here..." rows={5} style={{ ...styles.input, resize: "vertical", fontFamily: "monospace", fontSize: 12 }} autoFocus />
              <p style={styles.hint}>Get your offline key from <a href="https://app.promptshield.com/license" target="_blank" rel="noopener noreferrer" style={styles.link}>app.promptshield.com/license</a></p>
            </>
          )}

          <button type="submit" disabled={loading} style={{ ...styles.button, ...(loading ? styles.buttonDisabled : {}) }}>
            {loading ? "Please wait..." : mode === "login" ? "Sign In" : mode === "register" ? "Create Account" : "Apply License Key"}
          </button>
        </form>

        <div style={styles.footer}>
          <p style={styles.footerText}>
            {mode === "login" ? (<>Don't have an account? <button style={styles.linkButton} onClick={() => setMode("register")}>Create one</button></>) : mode === "register" ? (<>Already have an account? <button style={styles.linkButton} onClick={() => setMode("login")}>Sign in</button></>) : (<>Have an account? <button style={styles.linkButton} onClick={() => setMode("login")}>Sign in online</button></>)}
          </p>
          <p style={styles.footerText}>No internet? <button style={styles.linkButton} onClick={() => setMode("offline-key")}>Use an offline key</button></p>
        </div>
      </div>
    </div>
  );
}

function friendlyError(code: string): string {
  switch (code) {
    case "auth/user-not-found": case "auth/wrong-password": case "auth/invalid-credential": return "Invalid email or password";
    case "auth/email-already-in-use": return "An account with this email already exists";
    case "auth/weak-password": return "Password must be at least 6 characters";
    case "auth/invalid-email": return "Invalid email address";
    case "auth/too-many-requests": return "Too many attempts. Please try again later.";
    case "auth/network-request-failed": return "Network error. Check your connection.";
    case "auth/popup-blocked": return "Sign-in popup was blocked. Allow popups and try again.";
    case "auth/account-exists-with-different-credential": return "An account already exists with this email using a different sign-in method.";
    default: return code?.replace("auth/", "").replace(/-/g, " ") ?? "Authentication failed";
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: "flex", alignItems: "center", justifyContent: "center", height: "100vh", width: "100vw", background: "var(--bg-primary, #0d1117)", padding: 24 },
  card: { width: "100%", maxWidth: 420, background: "var(--bg-secondary, #161b22)", borderRadius: 12, border: "1px solid var(--border-color, #30363d)", padding: 32, boxShadow: "0 8px 32px rgba(0,0,0,0.4)" },
  header: { textAlign: "center" as const, marginBottom: 24 },
  title: { fontSize: 28, fontWeight: 700, color: "var(--accent-primary, #58a6ff)", margin: 0, letterSpacing: "-0.5px" },
  subtitle: { fontSize: 13, color: "var(--text-secondary, #8b949e)", margin: "4px 0 0 0" },
  tabs: { display: "flex", gap: 0, marginBottom: 20, borderBottom: "1px solid var(--border-color, #30363d)" },
  tab: { flex: 1, padding: "8px 0", background: "none", border: "none", borderBottom: "2px solid transparent", color: "var(--text-secondary, #8b949e)", fontSize: 13, cursor: "pointer", transition: "all 0.15s" },
  tabActive: { color: "var(--accent-primary, #58a6ff)", borderBottomColor: "var(--accent-primary, #58a6ff)" },
  error: { background: "rgba(248,81,73,0.1)", border: "1px solid rgba(248,81,73,0.4)", borderRadius: 6, padding: "8px 12px", color: "#f85149", fontSize: 13, marginBottom: 16 },
  socialContainer: { display: "flex", flexDirection: "column" as const, gap: 8, marginBottom: 16 },
  socialButton: { display: "flex", alignItems: "center", justifyContent: "center", gap: 10, padding: "10px 0", borderRadius: 6, border: "1px solid var(--border-color, #30363d)", background: "var(--bg-primary, #0d1117)", color: "var(--text-primary, #c9d1d9)", fontSize: 14, cursor: "pointer", transition: "border-color 0.15s, background 0.15s" },
  divider: { display: "flex", alignItems: "center", gap: 12, margin: "4px 0" },
  dividerLine: { flex: 1, height: 1, background: "var(--border-color, #30363d)" },
  dividerText: { fontSize: 12, color: "var(--text-muted, #6e7681)", textTransform: "uppercase" as const, letterSpacing: "0.5px" },
  form: { display: "flex", flexDirection: "column" as const, gap: 8 },
  label: { fontSize: 12, fontWeight: 600, color: "var(--text-secondary, #8b949e)", textTransform: "uppercase" as const, letterSpacing: "0.5px" },
  input: { padding: "10px 12px", borderRadius: 6, border: "1px solid var(--border-color, #30363d)", background: "var(--bg-primary, #0d1117)", color: "var(--text-primary, #c9d1d9)", fontSize: 14, outline: "none", marginBottom: 4 },
  button: { marginTop: 12, padding: "12px 0", borderRadius: 6, border: "none", background: "var(--accent-primary, #238636)", color: "#fff", fontSize: 14, fontWeight: 600, cursor: "pointer", transition: "opacity 0.15s" },
  buttonDisabled: { opacity: 0.6, cursor: "not-allowed" },
  hint: { fontSize: 12, color: "var(--text-muted, #6e7681)", margin: 0 },
  link: { color: "var(--accent-primary, #58a6ff)", textDecoration: "none" },
  footer: { marginTop: 20, textAlign: "center" as const },
  footerText: { fontSize: 13, color: "var(--text-secondary, #8b949e)", margin: "4px 0" },
  linkButton: { background: "none", border: "none", color: "var(--accent-primary, #58a6ff)", cursor: "pointer", padding: 0, fontSize: 13, textDecoration: "underline" },
};
