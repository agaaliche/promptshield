/** API client for the PromptShield licensing server + Tauri commands. */

import type {
  AuthTokens,
  LicenseResponse,
  LicenseStatus,
  SubscriptionInfo,
  UserInfo,
} from "./types";
import { useAppStore } from "./store";

// ── Licensing server URL ────────────────────────────────────────

const LICENSING_URL =
  import.meta.env.VITE_LICENSING_URL ?? "https://api.promptshield.com";

// ── Tauri invoke helper ─────────────────────────────────────────

/**
 * Dynamically import the Tauri invoke API.
 * Returns null when running outside Tauri (e.g. plain browser dev).
 */
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

// ── Licensing server HTTP client ────────────────────────────────

function getAuthHeaders(): Record<string, string> {
  const tokens = useAppStore.getState().authTokens;
  if (!tokens) return {};
  return { Authorization: `Bearer ${tokens.access_token}` };
}

async function licensingRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${LICENSING_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
    ...options,
  });

  if (res.status === 401) {
    // Try refresh
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry with new token
      const retryRes = await fetch(url, {
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
          ...(options.headers as Record<string, string> | undefined),
        },
        ...options,
      });
      if (!retryRes.ok) {
        const body = await retryRes.text();
        throw new Error(`Licensing API error ${retryRes.status}: ${body}`);
      }
      return retryRes.json();
    }
    // Refresh failed — clear auth
    useAppStore.getState().setAuthTokens(null);
    useAppStore.getState().setUserInfo(null);
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Licensing API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ── Auth endpoints ──────────────────────────────────────────────

export async function register(
  email: string,
  password: string,
): Promise<UserInfo> {
  return licensingRequest<UserInfo>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(
  email: string,
  password: string,
): Promise<AuthTokens> {
  const tokens = await licensingRequest<AuthTokens>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  useAppStore.getState().setAuthTokens(tokens);
  return tokens;
}

export async function tryRefreshToken(): Promise<boolean> {
  const tokens = useAppStore.getState().authTokens;
  if (!tokens?.refresh_token) return false;
  try {
    const newTokens = await fetch(`${LICENSING_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    if (!newTokens.ok) return false;
    const data: AuthTokens = await newTokens.json();
    useAppStore.getState().setAuthTokens(data);
    return true;
  } catch {
    return false;
  }
}

export async function logout(): Promise<void> {
  const tokens = useAppStore.getState().authTokens;
  if (tokens?.refresh_token) {
    try {
      await licensingRequest("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      });
    } catch {
      // Best effort
    }
  }
  useAppStore.getState().setAuthTokens(null);
  useAppStore.getState().setUserInfo(null);
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
