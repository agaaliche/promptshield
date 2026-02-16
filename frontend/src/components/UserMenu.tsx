/** User menu — avatar button at toolbar right edge.
 *
 * Click shows a dropdown with:
 *   - User name (from license payload email)
 *   - Email
 *   - Subscription plan + days remaining
 *   - Sign Out button (deactivates local license)
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { User, LogOut, Crown, Clock } from "lucide-react";
import { useLicenseStore, useSnackbarStore } from "../store";
import { deactivateLicense } from "../licenseApi";
import { auth } from "../firebaseConfig";

export default function UserMenu() {
  const { licenseStatus } = useLicenseStore();
  const { addSnackbar } = useSnackbarStore();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const handleSignOut = useCallback(async () => {
    setBusy(true);
    try {
      await deactivateLicense();
      addSnackbar("Signed out — license deactivated on this machine", "info");
    } catch {
      addSnackbar("Failed to sign out", "error");
    } finally {
      setBusy(false);
    }
  }, [addSnackbar]);

  if (!licenseStatus?.valid) return null;

  const payload = licenseStatus.payload;
  const email = payload?.email ?? auth.currentUser?.email ?? "Unknown";
  const daysLeft = licenseStatus.days_remaining;

  // Derive display values
  const initials = email
    .split("@")[0]
    .split(".")
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);

  const planLabel =
    payload?.plan === "free_trial"
      ? "Free Trial"
      : payload?.plan === "pro"
        ? "Standard Plan"
        : payload?.plan
          ? payload.plan.charAt(0).toUpperCase() + payload.plan.slice(1)
          : "Unknown";

  const planDetail =
    payload?.plan === "free_trial"
      ? daysLeft !== null
        ? `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`
        : ""
      : payload?.plan === "pro"
        ? "$14/mo"
        : daysLeft !== null
          ? `${daysLeft} day${daysLeft === 1 ? "" : "s"} left`
          : "";

  const statusColor =
    daysLeft !== null && daysLeft <= 7
      ? "#d29922"
      : "#3fb950";

  return (
    <div ref={menuRef} style={{ position: "relative" }}>
      {/* Avatar button */}
      <button
        onClick={() => setOpen(!open)}
        title={email}
        style={styles.avatarBtn}
      >
        <span style={styles.avatarCircle}>{initials || <User size={14} />}</span>
      </button>

      {/* Dropdown */}
      {open && (
        <div style={styles.dropdown}>
          {/* User header */}
          <div style={styles.userHeader}>
            <div style={styles.avatarLarge}>
              {initials || <User size={20} />}
            </div>
            <div style={styles.userInfo}>
              <div style={styles.userName}>{email.split("@")[0]}</div>
              <div style={styles.userEmail}>{email}</div>
            </div>
          </div>

          <div style={styles.divider} />

          {/* Subscription info */}
          <div style={styles.section}>
            <div style={styles.planRow}>
              <Crown size={14} style={{ color: statusColor, flexShrink: 0 }} />
              <span style={styles.planLabel}>{planLabel}</span>
            </div>
            {planDetail && (
              <div style={styles.planRow}>
                <Clock size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                <span style={styles.planDetail}>{planDetail}</span>
              </div>
            )}
          </div>

          <div style={styles.divider} />

          {/* Sign out */}
          <button
            onClick={handleSignOut}
            disabled={busy}
            style={styles.signOutBtn}
          >
            <LogOut size={14} />
            {busy ? "Signing out…" : "Sign Out"}
          </button>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  avatarBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: 2,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarCircle: {
    width: 30,
    height: 30,
    borderRadius: "50%",
    background: "var(--accent-primary, #2f81f7)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: 0.5,
    userSelect: "none",
  },
  dropdown: {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    width: 260,
    background: "var(--bg-secondary, #161b22)",
    border: "1px solid var(--border-color, #30363d)",
    borderRadius: 10,
    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
    zIndex: 1000,
    overflow: "hidden",
  },
  userHeader: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "14px 14px 10px",
  },
  avatarLarge: {
    width: 38,
    height: 38,
    borderRadius: "50%",
    background: "var(--accent-primary, #2f81f7)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 15,
    fontWeight: 700,
    letterSpacing: 0.5,
    flexShrink: 0,
  },
  userInfo: {
    overflow: "hidden",
  },
  userName: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userEmail: {
    fontSize: 12,
    color: "var(--text-muted, #8b949e)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  divider: {
    height: 1,
    background: "var(--border-color, #30363d)",
    margin: "0 10px",
  },
  section: {
    padding: "10px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  planRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  planLabel: {
    fontSize: 13,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
  },
  planDetail: {
    fontSize: 12,
    color: "var(--text-muted, #8b949e)",
  },
  signOutBtn: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    background: "none",
    border: "none",
    cursor: "pointer",
    color: "#f85149",
    fontSize: 13,
    fontWeight: 500,
    transition: "background 0.15s",
  },
};
