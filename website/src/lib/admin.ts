import { licensingFetch } from "./licensing";

const LICENSING_URL = process.env.NEXT_PUBLIC_LICENSING_URL || "https://licensing-server-455859748614.us-east4.run.app";

// ── Admin API helpers ───────────────────────────────────────────

export async function adminFetch(
  path: string,
  token: string,
  options: RequestInit = {}
) {
  return licensingFetch(path, token, options);
}

// ── Stats ───────────────────────────────────────────────────────

export interface AdminStats {
  total_users: number;
  total_subscriptions: number;
  active_subscriptions: number;
  total_machines: number;
  active_machines: number;
}

export async function getAdminStats(token: string): Promise<AdminStats> {
  return adminFetch("/admin/stats", token);
}

// ── Users ───────────────────────────────────────────────────────

export interface AdminUser {
  id: string;
  email: string;
  created_at: string;
  trial_used: boolean;
  has_billing: boolean;
  subscription_count: number;
  machine_count: number;
}

export interface AdminUserDetail {
  id: string;
  email: string;
  created_at: string;
  trial_used: boolean;
  stripe_customer_id: string | null;
  subscriptions: {
    id: string;
    plan: string;
    status: string;
    seats: number;
    period_end: string | null;
    created_at: string;
  }[];
  machines: {
    id: string;
    machine_fingerprint: string;
    machine_name: string;
    is_active: boolean;
    last_validated: string | null;
  }[];
}

export async function getAdminUsers(
  token: string,
  skip = 0,
  limit = 50
): Promise<AdminUser[]> {
  return adminFetch(`/admin/users?skip=${skip}&limit=${limit}`, token);
}

export async function getAdminUserDetail(
  token: string,
  userId: string
): Promise<AdminUserDetail> {
  return adminFetch(`/admin/users/${userId}`, token);
}

export async function revokeUserLicenses(
  token: string,
  userId: string
): Promise<{ ok: boolean; revoked_keys: number; deactivated_machines: number }> {
  return adminFetch(`/admin/users/${userId}/revoke`, token, {
    method: "POST",
  });
}

// ── Updates / Releases ──────────────────────────────────────────

export interface UpdateManifest {
  version: string;
  notes: string;
  pub_date: string;
  url: string;
  sha256: string;
  size: number;
  mandatory: boolean;
}

export async function getCurrentRelease(token: string): Promise<UpdateManifest | null> {
  try {
    return await adminFetch("/admin/releases/current", token);
  } catch {
    return null;
  }
}

export async function getAllReleases(token: string): Promise<UpdateManifest[]> {
  try {
    return await adminFetch("/admin/releases", token);
  } catch {
    return [];
  }
}

export async function publishRelease(
  token: string,
  manifest: UpdateManifest
): Promise<{ ok: boolean }> {
  return adminFetch("/admin/releases", token, {
    method: "POST",
    body: JSON.stringify(manifest),
  });
}

export async function deleteRelease(
  token: string,
  version: string
): Promise<{ ok: boolean }> {
  return adminFetch(`/admin/releases/${version}`, token, {
    method: "DELETE",
  });
}
