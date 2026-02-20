/** Account section — plan info, auto-validate toggle, deactivate/logout. */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, LogOut, Shield } from "../../icons";
import { useLicenseStore, useSnackbarStore } from "../../store";
import { Section } from "./settingsStyles";
import { SUPPORTED_LANGUAGES } from "../../i18n";
import PrivacyNoticeDialog from "../PrivacyNoticeDialog";

export default function AccountSection() {
  const { t, i18n } = useTranslation();
  const { licenseStatus, autoValidateOnline, setAutoValidateOnline } = useLicenseStore();
  const { addSnackbar } = useSnackbarStore();
  const [deactivating, setDeactivating] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);

  const payload = licenseStatus?.payload;

  const handleDeactivate = async () => {
    setDeactivating(true);
    try {
      const { deactivateLicense } = await import("../../licenseApi");
      await deactivateLicense();
      addSnackbar(t("account.licenseDeactivated"), "info");
    } catch {
      addSnackbar(t("account.failedToDeactivate"), "error");
    } finally {
      setDeactivating(false);
    }
  };

  const planLabel =
    payload?.plan === "free_trial" ? t("account.freeTrial")
    : payload?.plan === "pro" ? t("account.pro")
    : payload?.plan ?? t("account.noplan");

  const statusColor = licenseStatus?.valid
    ? (licenseStatus.days_remaining !== null && licenseStatus.days_remaining <= 7
        ? "#d29922"
        : "#3fb950")
    : "#f85149";

  const handleLogout = async () => {
    try {
      const { deactivateLicense } = await import("../../licenseApi");
      await deactivateLicense();
      addSnackbar(t("account.loggedOut"), "info");
    } catch {
      addSnackbar(t("account.failedToLogout"), "error");
    }
  };

  return (
    <Section>
      {payload && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor, flexShrink: 0 }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>{planLabel}</span>
            {licenseStatus?.days_remaining !== null && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
                {t("account.daysRemaining", { count: licenseStatus.days_remaining })}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 4 }}>
            <span>{t("account.email")} {payload.email}</span>
            <span>{t("account.seats")} {payload.seats}</span>
            <span>{t("account.expires")} {new Date(payload.expires).toLocaleDateString()}</span>
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
          {t("account.autoValidate")}
        </label>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0, lineHeight: 1.4 }}>
          {t("account.autoValidateHint")}
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
            {deactivating ? t("account.deactivating") : t("account.deactivateLicense")}
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
            <Globe size={12} /> {t("account.manageAccount")}
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
          <LogOut size={12} /> {t("account.logout")}
        </button>
      </div>

      {/* Language */}
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border-color)" }}>
        <p style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>{t("account.language")}</p>
        <select
          value={i18n.language?.substring(0, 2) ?? "en"}
          onChange={(e) => i18n.changeLanguage(e.target.value)}
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            border: "1px solid var(--border-color)",
            background: "var(--bg-secondary)",
            color: "var(--text-primary)",
            fontSize: 13,
            cursor: "pointer",
            width: "100%",
          }}
        >
          {SUPPORTED_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.flag} {lang.label}
            </option>
          ))}
        </select>
      </div>

      {/* Privacy & Legal */}
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border-color)" }}>
        <p style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>{t("account.privacyAndLegal")}</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            onClick={() => setShowPrivacy(true)}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--text-secondary)",
              fontSize: 12,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Shield size={12} /> {t("account.privacyPolicy")}
          </button>
          <a
            href="https://www.promptshield.com/terms"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              border: "1px solid var(--border-color)",
              background: "transparent",
              color: "var(--text-secondary)",
              fontSize: 12,
              cursor: "pointer",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Globe size={12} /> {t("account.termsOfService")}
          </a>
        </div>
      </div>

      <PrivacyNoticeDialog open={showPrivacy} onClose={() => setShowPrivacy(false)} />
    </Section>
  );
}
