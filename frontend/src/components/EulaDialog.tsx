/** EULA / Terms of Service acceptance dialog.
 *
 * Shown on first launch (or after TOS version bump) before any other UI.
 * Acceptance is stored in localStorage with the TOS version so we can
 * re-prompt when the terms are updated.
 */

import { useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { EULA_VERSION, recordEulaAcceptance } from "../eulaVersion";

interface Props {
  onAccepted: () => void;
}

export default function EulaDialog({ onAccepted }: Props) {
  const { t } = useTranslation();
  const [scrolledToEnd, setScrolledToEnd] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  // Callback ref pattern: runs once when the scrollable div mounts.
  // Avoids calling setState inside useEffect which React 19 warns about.
  const contentRefCallback = useCallback((el: HTMLDivElement | null) => {
    // Store ref for later use
    (contentRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    if (!el) return;

    // If content doesn't overflow, there's nothing to scroll
    if (el.scrollHeight <= el.clientHeight + 10) {
      setScrolledToEnd(true);
    }

    const checkScroll = () => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
      if (atBottom) setScrolledToEnd(true);
    };

    el.addEventListener("scroll", checkScroll);
  }, []);

  const handleAccept = () => {
    recordEulaAcceptance();
    onAccepted();
  };

  return (
    <div style={styles.backdrop}>
      <div style={styles.dialog} role="dialog" aria-modal="true" aria-label={t("eula.title")}>
        {/* Header */}
        <div style={styles.header}>
          <h2 style={styles.title}>{t("eula.title")}</h2>
          <p style={styles.subtitle}>
            {t("eula.subtitle")}
          </p>
        </div>

        {/* Scrollable TOS content */}
        <div ref={contentRefCallback} style={styles.content}>
          <TosContent />
        </div>

        {/* Scroll hint */}
        {!scrolledToEnd && (
          <div style={styles.scrollHint}>
            {t("eula.scrollHint")}
          </div>
        )}

        {/* Actions */}
        <div style={styles.actions}>
          <button
            className="btn-primary"
            disabled={!scrolledToEnd}
            onClick={handleAccept}
            style={styles.acceptBtn}
          >
            {t("eula.acceptButton")}
          </button>
          <p style={styles.declineNote}>
            {t("eula.disclaimer")}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Inline TOS text ──────────────────────────────────────────────
// Keep this as a component so it can be swapped for a fetched version later.

function TosContent() {
  const { t } = useTranslation();
  return (
    <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--text-secondary)" }}>
      <h3 style={sectionTitle}>1. Acceptance of Terms</h3>
      <p>
        By installing, accessing, or using promptShield ("the Software"), you agree
        to be bound by these Terms of Service ("Terms"). If you do not agree to
        these Terms, you must not use the Software.
      </p>

      <h3 style={sectionTitle}>2. License Grant</h3>
      <p>
        Subject to your compliance with these Terms and payment of applicable fees,
        we grant you a limited, non-exclusive, non-transferable, revocable license
        to install and use the Software on the number of machines permitted by your
        subscription plan. You may not sublicense, redistribute, reverse-engineer,
        decompile, or disassemble any part of the Software.
      </p>

      <h3 style={sectionTitle}>3. Account &amp; Machine Activation</h3>
      <p>
        You must create an account and activate the Software on each machine.
        Each subscription plan includes a defined number of seats, with each seat
        allowing activation on up to three machines. You are responsible for
        maintaining the confidentiality of your account credentials.
      </p>

      <h3 style={sectionTitle}>4. Data Processing &amp; Privacy</h3>
      <p>
        <strong>Local processing:</strong> All document anonymization, OCR, and
        PII detection is performed entirely on your local machine. Your documents
        are never uploaded to our servers.
      </p>
      <p style={{ marginTop: 8 }}>
        <strong>What we collect:</strong> We collect only the minimum data necessary
        to operate the licensing and update services: your email address, machine
        fingerprint (a hardware-derived hash — not your hardware serials), license
        activation timestamps, and anonymous crash reports (if enabled). We do not
        collect, store, or transmit any document content.
      </p>
      <p style={{ marginTop: 8 }}>
        <strong>Crash reporting:</strong> When enabled, anonymous error reports
        (stack traces, OS version, app version) are sent to our error monitoring
        service to help us fix bugs. No document content or personal data beyond
        your anonymized machine identifier is included.
      </p>

      <h3 style={sectionTitle}>5. Intellectual Property</h3>
      <p>
        The Software, including all code, models, documentation, and associated
        materials, is the proprietary property of the promptShield team and is
        protected by copyright and other intellectual property laws. These Terms
        do not transfer any ownership rights to you.
      </p>

      <h3 style={sectionTitle}>6. Limitation of Liability</h3>
      <p>
        The Software is provided "as is" without warranties of any kind. In no
        event shall the promptShield team be liable for any indirect, incidental,
        special, consequential, or punitive damages, including loss of data or
        profits, arising from your use of the Software. Our total liability shall
        not exceed the amount you paid for the Software in the twelve months
        preceding the claim.
      </p>

      <h3 style={sectionTitle}>7. Subscription &amp; Payment</h3>
      <p>
        Paid plans are billed on a recurring basis. You may cancel at any time;
        cancellation takes effect at the end of the current billing period. We
        reserve the right to change pricing with 30 days' notice. Refunds are
        handled according to our refund policy.
      </p>

      <h3 style={sectionTitle}>8. Updates</h3>
      <p>
        We may release updates to the Software from time to time. Some updates
        may be required for continued use. The auto-update feature, when enabled,
        will download and install updates automatically.
      </p>

      <h3 style={sectionTitle}>9. Termination</h3>
      <p>
        We may suspend or terminate your license if you breach these Terms. Upon
        termination, you must cease all use of the Software and delete all copies.
        Sections 4 through 6 survive termination.
      </p>

      <h3 style={sectionTitle}>10. Governing Law</h3>
      <p>
        These Terms are governed by the laws of the jurisdiction in which the
        promptShield team is incorporated, without regard to conflict of law
        principles.
      </p>

      <h3 style={sectionTitle}>11. Changes to Terms</h3>
      <p>
        We may update these Terms from time to time. When we make material changes,
        we will prompt you to re-accept the updated terms within the application.
        Continued use after acceptance constitutes agreement to the revised Terms.
      </p>

      <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-color)" }}>
        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {t("eula.versionLine", { version: EULA_VERSION })}
        </p>
      </div>
    </div>
  );
}

const sectionTitle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  color: "var(--text-primary)",
  marginTop: 20,
  marginBottom: 6,
};

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(0, 0, 0, 0.7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 999999, // Above everything
  },
  dialog: {
    background: "var(--bg-primary)",
    border: "1px solid var(--border-color)",
    borderRadius: 12,
    width: "min(620px, 90vw)",
    maxHeight: "85vh",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
  },
  header: {
    padding: "24px 28px 16px",
    borderBottom: "1px solid var(--border-color)",
  },
  title: {
    fontSize: 20,
    fontWeight: 700,
    color: "var(--text-primary)",
    margin: 0,
  },
  subtitle: {
    fontSize: 13,
    color: "var(--text-secondary)",
    marginTop: 6,
    marginBottom: 0,
  },
  content: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "20px 28px",
    minHeight: 0,
    maxHeight: "50vh",
    userSelect: "text" as const,
    WebkitUserSelect: "text" as const,
  },
  scrollHint: {
    textAlign: "center" as const,
    padding: "8px 0",
    fontSize: 12,
    color: "var(--accent-warning)",
    background: "var(--bg-secondary)",
    borderTop: "1px solid var(--border-color)",
  },
  actions: {
    padding: "16px 28px 24px",
    borderTop: "1px solid var(--border-color)",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 12,
  },
  acceptBtn: {
    padding: "10px 28px",
    fontSize: 14,
    fontWeight: 600,
    width: "100%",
  },
  declineNote: {
    fontSize: 11,
    color: "var(--text-muted)",
    textAlign: "center" as const,
    margin: 0,
    lineHeight: 1.5,
  },
};
