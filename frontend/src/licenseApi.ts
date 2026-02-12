/** API client for the PromptShield licensing server + Tauri commands.
 *
 * The desktop app is purely key-based. There is NO Firebase auth in the app.
 * Online license validation uses the machine fingerprint + existing license
 * blob as proof of prior authorization — no bearer tokens needed.
 */

import type {
  LicenseResponse,
  LicenseStatus,
  SubscriptionInfo,
} from "./types";
import { useAppStore } from "./store";

// ── Licensing server URL ────────────────────────────────────────

const LICENSING_URL =
  import.meta.env.VITE_LICENSING_URL ?? "https://api.promptshield.com";

// ── Tauri detection ─────────────────────────────────────────────

/** Returns true when running inside Tauri desktop shell. */
export function isTauri(): boolean {
  return "__TAURI_INTERNALS__" in window;
}

// ── Tauri invoke helper ─────────────────────────────────────────

async function tauriInvoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(cmd, args);
}

// ── Tauri license commands (Rust side) ──────────────────────────

export async function getMachineId(): Promise<string> {
  return tauriInvoke<string>("get_machine_id");
}

export async function getMachineName(): Promise<string> {
  return tauriInvoke<string>("get_machine_name");
}

export async function validateLocalLicense(): Promise<LicenseStatus> {
  return tauriInvoke<LicenseStatus>("validate_license");
}

export async function storeLocalLicense(blob: string): Promise<LicenseStatus> {
  return tauriInvoke<LicenseStatus>("store_license", { blob });
}

export async function clearLocalLicense(): Promise<void> {
  return tauriInvoke<void>("clear_license");
}

export async function startBackend(): Promise<string> {
  return tauriInvoke<string>("start_backend");
}

// ── Simple HTTP client (no auth headers) ────────────────────────

/**
 * Licensing API request. No bearer tokens — the machine fingerprint +
 * license blob in the request body serve as identity for validation.
 */
async function licensingRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${LICENSING_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string> | undefined),
    },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Licensing API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ── License endpoints ───────────────────────────────────────────

export async function activateLicense(
  machineFingerprint: string,
  machineName: string,
): Promise<LicenseResponse> {
  return licensingRequest<LicenseResponse>("/license/activate", {
    method: "POST",
    body: JSON.stringify({
      machine_fingerprint: machineFingerprint,
      machine_name: machineName,
    }),
  });
}

export async function validateLicenseOnline(
  machineFingerprint: string,
): Promise<LicenseResponse> {
  return licensingRequest<LicenseResponse>("/license/validate", {
    method: "POST",
    body: JSON.stringify({ machine_fingerprint: machineFingerprint }),
  });
}

export async function getLicenseStatus(): Promise<{
  valid: boolean;
  plan?: string;
  expires_at?: string;
  seats?: number;
  days_remaining?: number;
  message?: string;
}> {
  const machineFingerprint = await getMachineId();
  return licensingRequest("/license/status", {
    method: "POST",
    body: JSON.stringify({ machine_fingerprint: machineFingerprint }),
  });
}

// ── Billing endpoints (used from website, kept for completeness) ─

export async function createCheckout(
  successUrl?: string,
  cancelUrl?: string,
): Promise<{ checkout_url: string; session_id: string }> {
  return licensingRequest("/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ success_url: successUrl, cancel_url: cancelUrl }),
  });
}

export async function getSubscription(): Promise<SubscriptionInfo | null> {
  const machineFingerprint = await getMachineId();
  return licensingRequest<SubscriptionInfo | null>("/billing/subscription", {
    method: "POST",
    body: JSON.stringify({ machine_fingerprint: machineFingerprint }),
  });
}

export async function createBillingPortal(): Promise<{ portal_url: string }> {
  return licensingRequest("/billing/portal", { method: "POST" });
}

// ── Deactivation (replaces "logout") ────────────────────────────

/**
 * Deactivate the local license and reset the app to the key-paste screen.
 */
export async function deactivateLicense(): Promise<void> {
  await clearLocalLicense().catch(() => {});
  useAppStore.getState().setLicenseStatus(null);
  useAppStore.getState().setLicenseChecked(false);
}

// ── Full activation flow ────────────────────────────────────────

/**
 * Complete activation: get machine info → activate on server → store locally.
 * Returns the resulting LicenseStatus from the Rust side.
 */
export async function fullActivation(): Promise<LicenseStatus> {
  const machineId = await getMachineId();
  const machineName = await getMachineName();

  // Activate on licensing server
  const licenseResponse = await activateLicense(machineId, machineName);

  // Store the blob locally so the Rust code can verify it offline
  const status = await storeLocalLicense(licenseResponse.license_blob);
  useAppStore.getState().setLicenseStatus(status);

  return status;
}

/**
 * Online revalidation: re-verify with licensing server → refresh license blob.
 * Uses machine fingerprint as identity (no auth tokens needed).
 */
export async function revalidateLicense(): Promise<LicenseStatus> {
  const machineId = await getMachineId();

  const licenseResponse = await validateLicenseOnline(machineId);
  const status = await storeLocalLicense(licenseResponse.license_blob);
  useAppStore.getState().setLicenseStatus(status);

  return status;
}
