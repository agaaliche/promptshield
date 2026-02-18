/** User menu — shows user info in sidebar.
 *
 * Always visible:
 *   - Avatar with initials
 *   - User name (from license payload email)
 *   - Email
 *
 * On hover/click shows:
 *   - Subscription plan + days remaining
 *   - Sign Out button (deactivates local license)
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { User, LogOut, Crown, Clock, ChevronDown, ChevronUp } from "lucide-react";
import { useLicenseStore, useSnackbarStore } from "../store";
import { deactivateLicense } from "../licenseApi";
import { auth } from "../firebaseConfig";

export default function UserMenu() {
  const { licenseStatus } = useLicenseStore();
  const { addSnackbar } = useSnackbarStore();
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Close on outside click
  useEffect(() => {
    if (!expanded) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setExpanded(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [expanded]);

  // Close on Escape
  useEffect(() => {
    if (!expanded) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [expanded]);

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

  const handleMouseEnter = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    hoverTimeoutRef.current = setTimeout(() => setExpanded(true), 150);
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    hoverTimeoutRef.current = setTimeout(() => setExpanded(false), 300);
  }, []);

  if (!licenseStatus?.valid) return null;

  const payload = licenseStatus.payload;
  const email = payload?.email ?? auth.currentUser?.email ?? "Unknown";
  const daysLeft = licenseStatus.days_remaining;

  // Derive display values
  const userName = email.split("@")[0];
  const initials = userName
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
    <div
      ref={menuRef}
      style={styles.container}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Always visible: avatar + name + email */}
      <div
        style={styles.header}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={styles.avatarCircle}>
          {initials || <User size={14} />}
        </div>
        <div style={styles.userInfo}>
          <div style={styles.userName}>{userName}</div>
          <div style={styles.userEmail}>{email}</div>
        </div>
        {expanded ? <ChevronUp size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} /> : <ChevronDown size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />}
      </div>

      {/* Expandable section: subscription + logout */}
      {expanded && (
        <div style={styles.expandedSection}>
          {/* Subscription info */}
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
  container: {
    display: "flex",
    flexDirection: "column",
    borderRadius: 8,
    background: "var(--bg-tertiary, rgba(255,255,255,0.03))",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 10px",
    cursor: "pointer",
    transition: "background 0.15s",
  },
  avatarCircle: {
    width: 28,
    height: 28,
    borderRadius: "50%",
    background: "var(--accent-primary, #2f81f7)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.5,
    userSelect: "none",
    flexShrink: 0,
  },
  userInfo: {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
  },
  userName: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  userEmail: {
    fontSize: 10,
    color: "var(--text-muted, #8b949e)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  expandedSection: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    padding: "8px 10px",
    borderTop: "1px solid var(--border-color, #30363d)",
    background: "rgba(0,0,0,0.1)",
  },
  planRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  planLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
  },
  planDetail: {
    fontSize: 10,
    color: "var(--text-muted, #8b949e)",
  },
  signOutBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 8px",
    marginTop: 4,
    background: "none",
    border: "1px solid rgba(248,81,73,0.3)",
    borderRadius: 6,
    cursor: "pointer",
    color: "#f85149",
    fontSize: 11,
    fontWeight: 500,
    transition: "background 0.15s, border-color 0.15s",
  },
};
