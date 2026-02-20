/** Sentry crash-reporting initialization.
 *
 * Sends anonymous error reports (stack traces, OS/app version) to Sentry
 * so we can fix bugs in production. No document content or PII is collected.
 *
 * Configure by setting VITE_SENTRY_DSN in the environment or .env file.
 * When the DSN is not set, Sentry is disabled (no-op).
 */

import * as Sentry from "@sentry/react";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN ?? "";
const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? "0.1.0";
const ENVIRONMENT = import.meta.env.MODE; // "development" | "production"

/** Whether Sentry crash reporting is active. */
export const isSentryEnabled = !!SENTRY_DSN;

export function initSentry(): void {
  if (!SENTRY_DSN) {
    console.debug("[sentry] No DSN configured — crash reporting disabled");
    return;
  }

  Sentry.init({
    dsn: SENTRY_DSN,
    release: `promptshield@${APP_VERSION}`,
    environment: ENVIRONMENT,

    // Sample 100 % of errors, 10 % of transactions (performance)
    sampleRate: 1.0,
    tracesSampleRate: 0.1,

    // Scrub sensitive data from breadcrumbs
    beforeBreadcrumb(breadcrumb) {
      // Don't send URL breadcrumbs that might contain local file paths
      if (breadcrumb.category === "navigation") return null;
      return breadcrumb;
    },

    // Filter events before they are sent
    beforeSend(event) {
      // Strip any local file paths from stack frames
      if (event.exception?.values) {
        for (const exception of event.exception.values) {
          if (exception.stacktrace?.frames) {
            for (const frame of exception.stacktrace.frames) {
              // Replace absolute paths with just the filename
              if (frame.filename && !frame.filename.startsWith("http")) {
                const parts = frame.filename.replace(/\\/g, "/").split("/");
                frame.filename = parts[parts.length - 1];
              }
            }
          }
        }
      }
      return event;
    },

    // Don't send PII (IP addresses are anonymized by default in Sentry)
    sendDefaultPii: false,

    integrations: [
      Sentry.browserTracingIntegration(),
    ],
  });

  console.debug("[sentry] Crash reporting initialized");
}

/** Capture a manual error report. */
export function captureError(error: unknown, context?: Record<string, unknown>): void {
  if (!isSentryEnabled) return;

  if (error instanceof Error) {
    Sentry.captureException(error, { extra: context });
  } else {
    Sentry.captureMessage(String(error), { extra: context, level: "error" });
  }
}

/** Set the anonymous user identifier (machine fingerprint hash). */
export function setSentryUser(machineId: string): void {
  if (!isSentryEnabled) return;
  // Only send a hashed ID — no email, no name
  Sentry.setUser({ id: machineId });
}
