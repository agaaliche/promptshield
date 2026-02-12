/** License status indicator — shown in the sidebar.
 *
 * Displays plan, days remaining, and email from the license payload.
 * "Deactivate" clears the local key and returns to the key-paste screen.
 */

import { useState } from "react";
import { useAppStore } from "../store";
import { deactivateLicense } from "../licenseApi";

export default function LicenseStatus() {
  const { licenseStatus, addSnackbar } = useAppStore();
  const [busy, setBusy] = useState(false);

  if (!licenseStatus) return null;

  const { valid, payload, days_remaining } = licenseStatus;

  const handleDeactivate = async () => {
    setBusy(true);
    try {
      await deactivateLicense();
      addSnackbar("License deactivated", "info");
    } catch {
      addSnackbar("Failed to deactivate", "error");
    } finally {
      setBusy(false);
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
      {payload?.email && (
        <div style={styles.row}>
          <span style={styles.email} title={payload.email}>
            {payload.email}
          </span>
        </div>
      )}
      <button onClick={handleDeactivate} disabled={busy} style={styles.deactivateBtn}>
        {busy ? "..." : "Sign Out"}
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
  deactivateBtn: {
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
