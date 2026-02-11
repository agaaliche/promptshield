/** License status indicator — shown in the sidebar or settings. */

import { useAppStore } from "../store";
import { logout } from "../licenseApi";

export default function LicenseStatus() {
  const { licenseStatus, userInfo, addSnackbar, setLicenseStatus, setLicenseChecked } =
    useAppStore();

  if (!licenseStatus) return null;

  const { valid, payload, days_remaining } = licenseStatus;

  const handleLogout = async () => {
    try {
      await logout();
      setLicenseStatus(null);
      setLicenseChecked(false);
      addSnackbar("Logged out successfully", "info");
    } catch {
      addSnackbar("Logout failed", "error");
    }
  };

  const planLabel =
    payload?.plan === "free_trial"
      ? "Free Trial"
      : payload?.plan === "pro"
        ? "Pro"
        : payload?.plan ?? "—";

  const statusColor = valid
    ? days_remaining !== null && days_remaining <= 7
      ? "#d29922" // warning yellow
      : "#3fb950" // green
    : "#f85149"; // red

  return (
    <div style={styles.container}>
      <div style={styles.row}>
        <div style={{ ...styles.dot, background: statusColor }} />
        <span style={styles.planText}>{planLabel}</span>
        {days_remaining !== null && valid && (
          <span style={styles.daysText}>
            {days_remaining}d left
          </span>
        )}
      </div>
      {userInfo && (
        <div style={styles.row}>
          <span style={styles.email} title={userInfo.email}>
            {userInfo.email}
          </span>
        </div>
      )}
      <button onClick={handleLogout} style={styles.logoutBtn}>
        Sign Out
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: "8px 12px",
    borderTop: "1px solid var(--border-color, #30363d)",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    flexShrink: 0,
  },
  planText: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-primary, #c9d1d9)",
  },
  daysText: {
    fontSize: 11,
    color: "var(--text-secondary, #8b949e)",
    marginLeft: "auto",
  },
  email: {
    fontSize: 11,
    color: "var(--text-muted, #6e7681)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: 160,
  },
  logoutBtn: {
    marginTop: 4,
    padding: "4px 8px",
    borderRadius: 4,
    border: "1px solid var(--border-color, #30363d)",
    background: "transparent",
    color: "var(--text-secondary, #8b949e)",
    fontSize: 11,
    cursor: "pointer",
    alignSelf: "flex-start",
  },
};
