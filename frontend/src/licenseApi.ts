/** API client for the PromptShield licensing server + Tauri commands.
 *
 * Auth is delegated to Firebase. The licensing server verifies Firebase ID
 * tokens via the `Authorization: Bearer <idToken>` header. No custom JWT /
 * refresh-token logic is needed on the client side — Firebase SDK handles
 * token refresh transparently.
 */

import type {
  LicenseResponse,
  LicenseStatus,
  SubscriptionInfo,
  UserInfo,
} from "./types";
import { useAppStore } from "./store";
import { auth } from "./firebaseConfig";
import { signOut } from "firebase/auth";

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

/**
 * Web-mode license check: verifies Firebase user against the licensing server.
 * Returns a LicenseStatus-compatible object.
 */
export async function checkWebLicense(): Promise<LicenseStatus> {
  const user = auth.currentUser;
  if (!user) {
    return { valid: false, payload: null, error: "Not logged in", days_remaining: null };
  }
  try {
    // Sync user with backend (creates user row + trial if first time)
    await syncFirebaseUser();
    // Check licence status
    const ls = await getLicenseStatus();
    return {
      valid: ls.valid,
      payload: ls.plan
        ? { plan: ls.plan, email: user.email ?? "", seats: ls.seats ?? 1, machine_id: "web", issued: "", expires: ls.expires_at ?? "", v: 1 }
        : null,
      error: ls.valid ? null : (ls.message ?? "License invalid"),
      days_remaining: ls.days_remaining ?? null,
    };
  } catch {
    return { valid: false, payload: null, error: "Session expired", days_remaining: null };
  }
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

// ── Firebase auth header ────────────────────────────────────────

/** Get the current Firebase ID token for Authorization header. */
async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) return {};
  const idToken = await user.getIdToken();
  return { Authorization: `Bearer ${idToken}` };
}

async function licensingRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${LICENSING_URL}${path}`;
  const authHeaders = await getAuthHeaders();
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(options.headers as Record<string, string> | undefined),
    },
    ...options,
  });

  if (res.status === 401) {
    // Firebase token may have expired — force refresh and retry once
    const user = auth.currentUser;
    if (user) {
      try {
        const freshToken = await user.getIdToken(/* forceRefresh */ true);
        const retryRes = await fetch(url, {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${freshToken}`,
            ...(options.headers as Record<string, string> | undefined),
          },
          ...options,
        });
        if (!retryRes.ok) {
          const body = await retryRes.text();
          throw new Error(`Licensing API error ${retryRes.status}: ${body}`);
        }
        return retryRes.json();
      } catch {
        // Force-refresh also failed — sign out
      }
    }
    useAppStore.getState().setUserInfo(null);
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Licensing API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ── Auth: Firebase sync ─────────────────────────────────────────

/**
 * Sync the current Firebase user with the licensing backend.
 * The backend will create or update the local user row and auto-provision
 * a free trial subscription for first-time users.
 */
export async function syncFirebaseUser(): Promise<UserInfo> {
  const user = await licensingRequest<UserInfo>("/auth/sync", { method: "POST" });
  useAppStore.getState().setUserInfo(user);
  return user;
}

export async function logout(): Promise<void> {
  try {
    await signOut(auth);
  } catch {
    // Best effort
  }
  useAppStore.getState().setUserInfo(null);
  useAppStore.getState().setLicenseStatus(null);
  useAppStore.getState().setLicenseChecked(false);
  await clearLocalLicense().catch(() => {});
}

export async function getMe(): Promise<UserInfo> {
  const user = await licensingRequest<UserInfo>("/auth/me");
  useAppStore.getState().setUserInfo(user);
  return user;
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
  return licensingRequest("/license/status");
}

// ── Billing endpoints ───────────────────────────────────────────

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
  return licensingRequest<SubscriptionInfo | null>("/billing/subscription");
}

export async function createBillingPortal(): Promise<{ portal_url: string }> {
  return licensingRequest("/billing/portal", { method: "POST" });
}

// ── Full activation flow ────────────────────────────────────────

/**
 * Complete activation: authenticate → activate on server → store locally.
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
 * Monthly revalidation: re-authenticate online → refresh license blob.
 */
export async function revalidateLicense(): Promise<LicenseStatus> {
  const machineId = await getMachineId();

  const licenseResponse = await validateLicenseOnline(machineId);
  const status = await storeLocalLicense(licenseResponse.license_blob);
  useAppStore.getState().setLicenseStatus(status);

  return status;
}
