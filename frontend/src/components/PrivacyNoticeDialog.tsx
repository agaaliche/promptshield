/** In-app privacy notice dialog.
 *
 * Shows the privacy policy within the desktop app so users don't
 * need to visit the website. Also accessible from Settings → Account.
 */

import { useState } from "react";
import { X, ExternalLink } from "../icons";
import { useTranslation } from "react-i18next";

const PRIVACY_URL = "https://www.promptshield.com/privacy";
const TERMS_URL = "https://www.promptshield.com/terms";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function PrivacyNoticeDialog({ open, onClose }: Props) {
  const { t } = useTranslation();
  if (!open) return null;

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div
        style={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={t("privacy.title")}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={styles.header}>
          <h2 style={styles.title}>{t("privacy.title")}</h2>
          <button onClick={onClose} style={styles.closeBtn} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div style={styles.content}>
          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.dataOnMachine")}</h3>
            <p style={styles.text}>
              {t("privacy.dataOnMachineDesc")}
            </p>
          </section>

          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.whatWeCollect")}</h3>
            <ul style={styles.list}>
              <li>{t("privacy.collectLicense")}</li>
              <li>{t("privacy.collectCrash")}</li>
              <li>{t("privacy.collectUpdates")}</li>
            </ul>
          </section>

          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.whatWeDoNot")}</h3>
            <ul style={styles.list}>
              <li>{t("privacy.notDocContents")}</li>
              <li>{t("privacy.notDetectedPII")}</li>
              <li>{t("privacy.notScreenshots")}</li>
              <li>{t("privacy.notVaultKeys")}</li>
              <li>{t("privacy.notAnalytics")}</li>
            </ul>
          </section>

          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.thirdParty")}</h3>
            <ul style={styles.list}>
              <li>{t("privacy.thirdFirebase")}</li>
              <li>{t("privacy.thirdStripe")}</li>
              <li>{t("privacy.thirdSentry")}</li>
            </ul>
          </section>

          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.dataRetention")}</h3>
            <p style={styles.text}>
              {t("privacy.dataRetentionDesc")}
            </p>
          </section>

          <section style={styles.section}>
            <h3 style={styles.sectionTitle}>{t("privacy.yourRights")}</h3>
            <p style={styles.text}>
              {t("privacy.yourRightsDesc")}
            </p>
          </section>
        </div>

        <div style={styles.footer}>
          <a href={PRIVACY_URL} target="_blank" rel="noopener noreferrer" style={styles.link}>
            <ExternalLink size={12} /> {t("privacy.fullPrivacyPolicy")}
          </a>
          <a href={TERMS_URL} target="_blank" rel="noopener noreferrer" style={styles.link}>
            <ExternalLink size={12} /> {t("privacy.fullTermsOfService")}
          </a>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={styles.doneBtn}>{t("common.done")}</button>
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.6)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10000,
  },
  dialog: {
    background: "var(--bg-secondary)",
    borderRadius: 12,
    border: "1px solid var(--border-color)",
    width: 600,
    maxWidth: "92vw",
    maxHeight: "80vh",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 16px 48px rgba(0,0,0,0.4)",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "16px 24px",
    borderBottom: "1px solid var(--border-color)",
  },
  title: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: 0,
  },
  closeBtn: {
    background: "transparent",
    border: "none",
    color: "var(--text-muted)",
    cursor: "pointer",
    padding: 4,
    borderRadius: 4,
  },
  content: {
    flex: 1,
    overflowY: "auto",
    padding: "20px 24px",
  },
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--text-primary)",
    marginBottom: 8,
  },
  text: {
    fontSize: 13,
    color: "var(--text-secondary)",
    lineHeight: 1.6,
    margin: 0,
  },
  list: {
    fontSize: 13,
    color: "var(--text-secondary)",
    lineHeight: 1.7,
    paddingLeft: 20,
    margin: 0,
  },
  footer: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "12px 24px",
    borderTop: "1px solid var(--border-color)",
  },
  link: {
    fontSize: 12,
    color: "var(--accent-primary)",
    textDecoration: "none",
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
  },
  doneBtn: {
    padding: "6px 16px",
    background: "var(--accent-primary)",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
};
