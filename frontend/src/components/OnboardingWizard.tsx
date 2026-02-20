/** Onboarding wizard — shown on first launch after EULA acceptance.
 *
 * Steps:
 *   1. Welcome + language selection
 *   2. Quick feature overview
 *   3. Import first document (optional)
 *
 * Completion is stored in localStorage so the wizard only shows once.
 */

import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Upload, Globe, Shield, ArrowRight, ArrowLeft, Check, FileText, Sparkles } from "../icons";
import { useDetectionStore } from "../store";
import { updateSettings, logError } from "../api";
import { useDocumentUpload, ACCEPTED_FILE_TYPES } from "../hooks/useDocumentUpload";

const ONBOARDING_KEY = "promptshield_onboarding_completed";
const ONBOARDING_VERSION = "1";

export function hasCompletedOnboarding(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) === ONBOARDING_VERSION;
  } catch {
    return false;
  }
}

export function recordOnboardingComplete(): void {
  try {
    localStorage.setItem(ONBOARDING_KEY, ONBOARDING_VERSION);
  } catch {
    /* storage unavailable */
  }
}

const LANGUAGES = [
  { code: "auto", label: "Auto-detect", flag: "🌐" },
  { code: "en", label: "English", flag: "🇬🇧" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "it", label: "Italiano", flag: "🇮🇹" },
  { code: "pt", label: "Português", flag: "🇵🇹" },
  { code: "nl", label: "Nederlands", flag: "🇳🇱" },
] as const;

interface Props {
  onComplete: () => void;
  backendReady: boolean;
}

export default function OnboardingWizard({ onComplete, backendReady }: Props) {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [selectedLang, setSelectedLang] = useState("auto");
  const { setDetectionSettings } = useDetectionStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileChosen, setFileChosen] = useState(false);

  const { handleFiles } = useDocumentUpload({
    onBeforeUpload: () => setFileChosen(true),
  });

  const handleFinish = useCallback(() => {
    // Persist language choice
    setDetectionSettings({ detection_language: selectedLang });
    if (backendReady) {
      updateSettings({ detection_language: selectedLang }).catch(logError("onboarding-lang"));
    }
    recordOnboardingComplete();
    onComplete();
  }, [selectedLang, setDetectionSettings, backendReady, onComplete]);

  const steps = [
    // Step 0: Welcome + Language
    <div key="welcome" style={styles.stepContent}>
      <div style={styles.iconCircle}>
        <Shield size={40} color="var(--accent-primary)" />
      </div>
      <h2 style={styles.stepTitle}>{t("onboarding.welcomeTitle")}</h2>
      <p style={styles.stepDesc}>
        {t("onboarding.welcomeDescription")}
      </p>
      <div style={styles.langSection}>
        <label style={styles.langLabel}>
          <Globe size={16} /> {t("onboarding.documentLanguage")}
        </label>
        <p style={styles.langHint}>
          {t("onboarding.languageHint")}
        </p>
        <div style={styles.langGrid}>
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => setSelectedLang(lang.code)}
              style={{
                ...styles.langBtn,
                ...(selectedLang === lang.code ? styles.langBtnActive : {}),
              }}
              aria-pressed={selectedLang === lang.code}
            >
              <span style={{ fontSize: 20 }}>{lang.flag}</span>
              <span>{lang.code === "auto" ? t("onboarding.autoDetect") : lang.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>,

    // Step 1: Feature overview
    <div key="features" style={styles.stepContent}>
      <h2 style={styles.stepTitle}>{t("onboarding.howItWorks")}</h2>
      <div style={styles.featureList}>
        <div style={styles.featureItem}>
          <div style={styles.featureIcon}><Upload size={24} /></div>
          <div>
            <strong style={styles.featureHead}>{t("onboarding.stepUpload")}</strong>
            <p style={styles.featureDesc}>{t("onboarding.stepUploadDesc")}</p>
          </div>
        </div>
        <div style={styles.featureItem}>
          <div style={styles.featureIcon}><Sparkles size={24} /></div>
          <div>
            <strong style={styles.featureHead}>{t("onboarding.stepDetect")}</strong>
            <p style={styles.featureDesc}>{t("onboarding.stepDetectDesc")}</p>
          </div>
        </div>
        <div style={styles.featureItem}>
          <div style={styles.featureIcon}><Shield size={24} /></div>
          <div>
            <strong style={styles.featureHead}>{t("onboarding.stepReview")}</strong>
            <p style={styles.featureDesc}>{t("onboarding.stepReviewDesc")}</p>
          </div>
        </div>
        <div style={styles.featureItem}>
          <div style={styles.featureIcon}><FileText size={24} /></div>
          <div>
            <strong style={styles.featureHead}>{t("onboarding.stepRestore")}</strong>
            <p style={styles.featureDesc}>{t("onboarding.stepRestoreDesc")}</p>
          </div>
        </div>
      </div>
    </div>,

    // Step 2: Import first document
    <div key="import" style={styles.stepContent}>
      <div style={styles.iconCircle}>
        <Upload size={40} color="var(--accent-primary)" />
      </div>
      <h2 style={styles.stepTitle}>{t("onboarding.importTitle")}</h2>
      <p style={styles.stepDesc}>
        {backendReady
          ? t("onboarding.importDescription")
          : t("onboarding.backendNotReady")}
      </p>
      {backendReady && (
        <div
          style={styles.dropArea}
          onClick={() => fileRef.current?.click()}
          role="button"
          tabIndex={0}
          aria-label={t("onboarding.clickToChoose")}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileRef.current?.click(); }}
        >
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_FILE_TYPES}
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.length) handleFiles(e.target.files);
              e.target.value = "";
            }}
          />
          {fileChosen ? (
            <>
              <Check size={32} color="var(--accent-success)" />
              <span style={{ color: "var(--accent-success)", fontWeight: 600 }}>{t("onboarding.fileQueued")}</span>
            </>
          ) : (
            <>
              <Upload size={32} color="var(--text-muted)" />
              <span style={{ color: "var(--text-secondary)" }}>{t("onboarding.clickToChoose")}</span>
            </>
          )}
        </div>
      )}
    </div>,
  ];

  const isLast = step === steps.length - 1;

  return (
    <div style={styles.backdrop}>
      <div style={styles.dialog} role="dialog" aria-modal="true" aria-label={t("onboarding.welcomeTitle")}>
        {/* Progress dots */}
        <div style={styles.dots}>
          {steps.map((_, i) => (
            <div
              key={i}
              style={{
                ...styles.dot,
                ...(i === step ? styles.dotActive : {}),
                ...(i < step ? styles.dotDone : {}),
              }}
            />
          ))}
        </div>

        {/* Step content */}
        {steps[step]}

        {/* Navigation */}
        <div style={styles.nav}>
          {step > 0 ? (
            <button style={styles.backBtn} onClick={() => setStep(step - 1)}>
              <ArrowLeft size={16} /> {t("common.back")}
            </button>
          ) : (
            <div />
          )}
          <div style={{ display: "flex", gap: 8 }}>
            {isLast && (
              <button style={styles.skipBtn} onClick={handleFinish}>
                {fileChosen ? t("common.done") : t("onboarding.skipAndFinish")}
              </button>
            )}
            {!isLast && (
              <button style={styles.nextBtn} onClick={() => setStep(step + 1)}>
                {t("common.next")} <ArrowRight size={16} />
              </button>
            )}
            {isLast && fileChosen && (
              <button style={styles.nextBtn} onClick={handleFinish}>
                <Check size={16} /> {t("onboarding.getStarted")}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10000,
  },
  dialog: {
    background: "var(--bg-secondary)",
    borderRadius: 16,
    border: "1px solid var(--border-color)",
    width: 560,
    maxWidth: "92vw",
    maxHeight: "88vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 24px 48px rgba(0,0,0,0.4)",
  },
  dots: {
    display: "flex",
    justifyContent: "center",
    gap: 8,
    padding: "20px 0 8px",
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "var(--border-color)",
    transition: "all 0.2s",
  },
  dotActive: {
    background: "var(--accent-primary)",
    transform: "scale(1.3)",
  },
  dotDone: {
    background: "var(--accent-success)",
  },
  stepContent: {
    padding: "24px 32px",
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 16,
  },
  iconCircle: {
    width: 80,
    height: 80,
    borderRadius: "50%",
    background: "var(--bg-surface)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  stepTitle: {
    fontSize: 22,
    fontWeight: 700,
    color: "var(--text-primary)",
    textAlign: "center" as const,
  },
  stepDesc: {
    fontSize: 14,
    color: "var(--text-secondary)",
    textAlign: "center" as const,
    maxWidth: 420,
    lineHeight: 1.6,
  },
  langSection: {
    width: "100%",
    marginTop: 8,
  },
  langLabel: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 13,
    fontWeight: 600,
    color: "var(--text-primary)",
    marginBottom: 4,
  },
  langHint: {
    fontSize: 12,
    color: "var(--text-muted)",
    marginBottom: 12,
  },
  langGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
    gap: 8,
  },
  langBtn: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    background: "var(--bg-surface)",
    border: "1px solid var(--border-color)",
    borderRadius: 8,
    color: "var(--text-secondary)",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.15s",
  },
  langBtnActive: {
    borderColor: "var(--accent-primary)",
    background: "rgba(74, 158, 255, 0.1)",
    color: "var(--text-primary)",
  },
  featureList: {
    display: "flex",
    flexDirection: "column",
    gap: 20,
    width: "100%",
    marginTop: 8,
  },
  featureItem: {
    display: "flex",
    gap: 16,
    alignItems: "flex-start",
  },
  featureIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    background: "var(--bg-surface)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "var(--accent-primary)",
    flexShrink: 0,
  },
  featureHead: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--text-primary)",
  },
  featureDesc: {
    fontSize: 13,
    color: "var(--text-secondary)",
    marginTop: 2,
    lineHeight: 1.5,
  },
  dropArea: {
    width: "100%",
    border: "2px dashed var(--border-color)",
    borderRadius: 12,
    padding: "32px 24px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 12,
    cursor: "pointer",
    transition: "border-color 0.2s",
    marginTop: 8,
  },
  nav: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "16px 32px 24px",
    borderTop: "1px solid var(--border-color)",
  },
  backBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 16px",
    background: "transparent",
    border: "1px solid var(--border-color)",
    borderRadius: 8,
    color: "var(--text-secondary)",
    fontSize: 13,
    cursor: "pointer",
  },
  nextBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 20px",
    background: "var(--accent-primary)",
    border: "none",
    borderRadius: 8,
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },
  skipBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 16px",
    background: "transparent",
    border: "1px solid var(--border-color)",
    borderRadius: 8,
    color: "var(--text-muted)",
    fontSize: 13,
    cursor: "pointer",
  },
};
