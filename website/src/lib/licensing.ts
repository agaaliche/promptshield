const LICENSING_URL = process.env.NEXT_PUBLIC_LICENSING_URL || "https://api.promptshield.ca";

export async function licensingFetch(
  path: string,
  token: string,
  options: RequestInit = {}
) {
  const res = await fetch(`${LICENSING_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export async function getOrCreateUser(token: string) {
  try {
    return await licensingFetch("/auth/me", token);
  } catch {
    // User doesn't exist yet → create via sync
    return await licensingFetch("/auth/sync", token, { method: "POST" });
  }
}

export async function getLicenseStatus(token: string) {
  return licensingFetch("/license/status", token);
}

export async function getMachines(token: string) {
  return licensingFetch("/license/machines", token);
}

export async function deactivateMachine(token: string, machineId: string) {
  return licensingFetch(`/license/machines/${machineId}`, token, {
    method: "DELETE",
  });
}
