/** Account section — plan info, auto-validate toggle, deactivate/logout. */

import { useState } from "react";
import { User, Globe, LogOut } from "lucide-react";
import { useLicenseStore, useSnackbarStore } from "../../store";
import { Section } from "./settingsStyles";

export default function AccountSection() {
  const { licenseStatus, autoValidateOnline, setAutoValidateOnline } = useLicenseStore();
  const { addSnackbar } = useSnackbarStore();
  const [deactivating, setDeactivating] = useState(false);

  const payload = licenseStatus?.payload;

  const handleDeactivate = async () => {
    setDeactivating(true);
    try {
      const { deactivateLicense } = await import("../../licenseApi");
      await deactivateLicense();
      addSnackbar("License deactivated", "info");
    } catch {
      addSnackbar("Failed to deactivate license", "error");
    } finally {
      setDeactivating(false);
    }
  };

  const planLabel =
    payload?.plan === "free_trial" ? "Free Trial"
    : payload?.plan === "pro" ? "Pro"
    : payload?.plan ?? "—";

  const statusColor = licenseStatus?.valid
    ? (licenseStatus.days_remaining !== null && licenseStatus.days_remaining <= 7
        ? "#d29922"
        : "#3fb950")
    : "#f85149";

  const handleLogout = async () => {
    try {
      const { deactivateLicense } = await import("../../licenseApi");
      await deactivateLicense();
      addSnackbar("Logged out", "info");
    } catch {
      addSnackbar("Failed to log out", "error");
    }
  };

  return (
    <Section title="Account" icon={<User size={16} />}>
      {payload && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor, flexShrink: 0 }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>{planLabel}</span>
            {licenseStatus?.days_remaining !== null && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
                {licenseStatus.days_remaining}d remaining
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 4 }}>
            <span>Email: {payload.email}</span>
            <span>Seats: {payload.seats}</span>
            <span>Expires: {new Date(payload.expires).toLocaleDateString()}</span>
          </div>
        </div>
      )}

      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={autoValidateOnline}
            onChange={(e) => setAutoValidateOnline(e.target.checked)}
          />
          Automatically validate license online
        </label>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, lineHeight: 1.4 }}>
          When enabled, the app silently refreshes your license key on launch when internet is available.
          Your key works offline for up to 30 days between validations.
        </p>
      </div>

      <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={handleDeactivate}
            disabled={deactivating}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--text-secondary)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            {deactivating ? "Deactivating..." : "Deactivate License"}
          </button>
          <a
            href="https://promptshield.ca"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--accent-primary)",
              fontSize: 12,
              cursor: "pointer",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Globe size={12} /> Manage Account
          </a>
        </div>
        <button
          onClick={handleLogout}
          style={{
            padding: "6px 12px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "transparent",
            color: "var(--accent-danger, #f85149)",
            fontSize: 12,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <LogOut size={12} /> Logout
        </button>
      </div>
    </Section>
  );
}
