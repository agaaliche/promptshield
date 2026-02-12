/** API client for the PromptShield licensing server + Tauri commands.
 *
 * Online sign-in uses the Firebase Auth SDK (email/password + Google).
 * After sign-in the ID token is sent to the licensing server which returns
 * an Ed25519-signed license blob. Once stored locally the app works offline.
 */

import {
  signInWithEmailAndPassword,
  signInWithPopup,
  onAuthStateChanged,
  signOut,
} from "firebase/auth";
import { auth, googleProvider } from "./firebaseConfig";
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

// ── Tauri license commands (with browser-dev fallbacks) ─────────

/**
 * Generate a stable-ish machine fingerprint.
 * In Tauri → Rust-generated hardware ID.
 * In browser → fingerprint from navigator + random UUID cached in localStorage.
 */
export async function getMachineId(): Promise<string> {
  if (isTauri()) return tauriInvoke<string>("get_machine_id");
  // Browser fallback for development / testing
  let id = localStorage.getItem("ps_dev_machine_id");
  if (!id) {
    id = `browser-${crypto.randomUUID()}`;
    localStorage.setItem("ps_dev_machine_id", id);
  }
  return id;
}

export async function getMachineName(): Promise<string> {
  if (isTauri()) return tauriInvoke<string>("get_machine_name");
  return `${navigator.userAgent.slice(0, 40)} (dev)`;
}

export async function validateLocalLicense(): Promise<LicenseStatus> {
  if (isTauri()) return tauriInvoke<LicenseStatus>("validate_license");
  // Browser fallback: check localStorage blob
  const blob = localStorage.getItem("ps_dev_license_blob");
  if (!blob) return { valid: false, payload: null, error: "No license found", days_remaining: null };
  // Can't Ed25519 verify in browser — reconstruct from stored payload
  try {
    const stored = JSON.parse(localStorage.getItem("ps_dev_license_payload") ?? "null");
    if (stored) {
      return { valid: true, payload: stored, error: null, days_remaining: stored.days_remaining ?? 99 };
    }
  } catch { /* ignore parse errors */ }
  return { valid: true, payload: null, error: null, days_remaining: 99 };
}

export async function storeLocalLicense(blob: string): Promise<LicenseStatus> {
  if (isTauri()) return tauriInvoke<LicenseStatus>("store_license", { blob });
  // Browser fallback: persist in localStorage and decode payload
  localStorage.setItem("ps_dev_license_blob", blob);
  // Try to decode the license blob: format is "base64(payload_json).base64(signature)"
  let payload: import("./types").LicensePayload | null = null;
  let daysRemaining: number | null = 99;
  try {
    const parts = blob.split(".", 2);
    const decoded = JSON.parse(atob(parts[0]));
    payload = {
      email: decoded.email ?? "unknown",
      plan: decoded.plan ?? "unknown",
      seats: decoded.seats ?? 1,
      machine_id: decoded.machine_id ?? "",
      issued: decoded.issued ?? new Date().toISOString(),
      expires: decoded.expires ?? "",
      v: decoded.v ?? 1,
    };
    if (decoded.expires) {
      const msLeft = new Date(decoded.expires).getTime() - Date.now();
      daysRemaining = Math.max(0, Math.ceil(msLeft / 86_400_000));
    }
    // Persist decoded payload for validateLocalLicense fallback
    localStorage.setItem("ps_dev_license_payload", JSON.stringify({ ...payload, days_remaining: daysRemaining }));
  } catch { /* blob decode failed — still valid, just no payload detail */ }
  return { valid: true, payload, error: null, days_remaining: daysRemaining };
}

export async function clearLocalLicense(): Promise<void> {
  if (isTauri()) return tauriInvoke<void>("clear_license");
  localStorage.removeItem("ps_dev_license_blob");
}

export async function startBackend(): Promise<string> {
  return tauriInvoke<string>("start_backend");
}

// ── HTTP client (auto-attaches Firebase bearer token) ───────────

/**
 * Licensing API request. Automatically attaches the current Firebase
 * user's ID token as a Bearer header when a user is signed in.
 */
async function licensingRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${LICENSING_URL}${path}`;
  const authHeaders: Record<string, string> = {};
  const user = auth.currentUser;
  if (user) {
    try {
      const idToken = await user.getIdToken();
      authHeaders["Authorization"] = `Bearer ${idToken}`;
    } catch {
      // Token refresh failed — proceed without auth (offline)
    }
  }
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
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

/**
 * Licensing API request with a Firebase bearer token for auth.
 */
async function authenticatedRequest<T>(
  path: string,
  idToken: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${LICENSING_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
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

// ── Shared activation helper ────────────────────────────────────

/**
 * Given a Firebase ID token, verify the user exists on the licensing backend,
 * activate the license for this machine, and store the blob locally.
 *
 * Account creation only happens on promptshield.ca — the app is sign-in only.
 * Used by both email/password and Google sign-in flows.
 */
async function activateWithToken(idToken: string): Promise<LicenseStatus> {
  // 1. Verify user exists on licensing backend (does NOT create accounts)
  const url = `${LICENSING_URL}/auth/me`;
  const meRes = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
  });

  if (!meRes.ok) {
    // Sign out of Firebase since activation won't proceed
    await signOut(auth).catch(() => {});
    if (meRes.status === 404 || meRes.status === 401) {
      throw new Error(
        "No account found. Please sign up at promptshield.ca first.",
      );
    }
    const body = await meRes.text();
    throw new Error(`Licensing server error: ${body}`);
  }

  // 2. Activate license for this machine
  const machineId = await getMachineId();
  const machineName = await getMachineName();

  const licenseResponse = await authenticatedRequest<LicenseResponse>(
    "/license/activate",
    idToken,
    {
      method: "POST",
      body: JSON.stringify({
        machine_fingerprint: machineId,
        machine_name: machineName,
      }),
    },
  );

  // 3. Store the Ed25519-signed blob locally
  const status = await storeLocalLicense(licenseResponse.license_blob);
  useAppStore.getState().setLicenseStatus(status);

  // 4. In Tauri mode, sign out of Firebase — we only need the local key.
  //    In browser mode, keep the session so revalidation can use the token.
  if (isTauri()) {
    await signOut(auth).catch(() => {});
  }

  return status;
}

// ── Online sign-in (Firebase Auth SDK) ──────────────────────────

/**
 * Sign in with email + password, then activate the license.
 */
export async function signInOnline(
  email: string,
  password: string,
): Promise<LicenseStatus> {
  try {
    const cred = await signInWithEmailAndPassword(auth, email, password);
    const idToken = await cred.user.getIdToken();
    return await activateWithToken(idToken);
  } catch (e: any) {
    throw new Error(friendlyFirebaseError(e.code));
  }
}

const GOOGLE_REDIRECT_KEY = "ps_google_redirect";

/**
 * Sign in with Google.
 *
 * Uses signInWithPopup but races it with onAuthStateChanged — if COOP
 * headers prevent the popup promise from resolving, the auth-state
 * listener picks up the signed-in user instead.
 */
export async function signInWithGoogle(): Promise<LicenseStatus> {
  return new Promise<LicenseStatus>((resolve, reject) => {
    let settled = false;

    function finish(p: Promise<LicenseStatus>) {
      if (settled) return;
      settled = true;
      unsubscribe();
      clearTimeout(timer);
      p.then(resolve, reject);
    }

    // Fallback: listen for Firebase detecting the user via auth state
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user && !settled) {
        finish(
          user.getIdToken().then((t) => activateWithToken(t)),
        );
      }
    });

    // Primary: signInWithPopup
    signInWithPopup(auth, googleProvider)
      .then((cred) => {
        if (!settled) {
          finish(
            cred.user.getIdToken().then((t) => activateWithToken(t)),
          );
        }
      })
      .catch((e) => {
        if (settled) return;
        settled = true;
        unsubscribe();
        clearTimeout(timer);
        if (e.code === "auth/popup-closed-by-user") {
          reject(new Error("Sign-in cancelled"));
        } else {
          reject(new Error(friendlyFirebaseError(e.code)));
        }
      });

    // Safety net timeout
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        unsubscribe();
        reject(new Error("Sign-in timed out. Please try again."));
      }
    }, 30_000);
  });
}

/**
 * No-op kept for API compatibility — redirect approach removed.
 */
export async function handleGoogleRedirectResult(): Promise<LicenseStatus | null> {
  return null;
}

function friendlyFirebaseError(code?: string): string {
  if (!code) return "Authentication failed";
  switch (code) {
    case "auth/user-not-found":
    case "auth/wrong-password":
    case "auth/invalid-credential":
      return "Invalid email or password";
    case "auth/user-disabled":
      return "This account has been disabled";
    case "auth/too-many-requests":
      return "Too many attempts. Please try again later.";
    case "auth/network-request-failed":
      return "Network error. Check your internet connection.";
    case "auth/popup-blocked":
      return "Sign-in popup was blocked. Allow popups and try again.";
    case "auth/account-exists-with-different-credential":
      return "An account already exists with this email using a different sign-in method.";
    default:
      return code?.replace("auth/", "").replace(/-/g, " ") ?? "Authentication failed";
  }
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
  // Also clear cached payload from browser fallback
  localStorage.removeItem("ps_dev_license_payload");
  // Sign out of Firebase (clears browser session)
  await signOut(auth).catch(() => {});
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
