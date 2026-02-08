/** API client for communicating with the Python sidecar backend. */

import type {
  AnonymizeResponse,
  BBox,
  DetectionResult,
  DetokenizeResponse,
  DocumentInfo,
  LLMStatus,
  PIIRegion,
  RegionAction,
  TokenMapping,
  UploadResponse,
  VaultStats,
} from "./types";

// In dev, Vite proxy forwards /api → backend.
// In production (Tauri), set via setBaseUrl() to the sidecar port.
let BASE_URL = "";

export function setBaseUrl(url: string) {
  BASE_URL = url;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers as Record<string, string> },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ──────────────────────────────────────────────
// Documents
// ──────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Upload failed: ${body}`);
  }

  return res.json();
}

export async function getDocument(docId: string): Promise<DocumentInfo> {
  return request<DocumentInfo>(`/api/documents/${docId}`);
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  return request<DocumentInfo[]>("/api/documents");
}

export function getPageBitmapUrl(docId: string, pageNumber: number): string {
  return `${BASE_URL}/api/documents/${docId}/pages/${pageNumber}/bitmap`;
}

// ──────────────────────────────────────────────
// Detection
// ──────────────────────────────────────────────

export async function detectPII(docId: string): Promise<DetectionResult> {
  return request<DetectionResult>(`/api/documents/${docId}/detect`, {
    method: "POST",
  });
}

export async function getRegions(
  docId: string,
  pageNumber?: number
): Promise<PIIRegion[]> {
  const params = pageNumber ? `?page_number=${pageNumber}` : "";
  return request<PIIRegion[]>(`/api/documents/${docId}/regions${params}`);
}

export async function setRegionAction(
  docId: string,
  regionId: string,
  action: RegionAction
): Promise<void> {
  await request(`/api/documents/${docId}/regions/${regionId}/action`, {
    method: "PUT",
    body: JSON.stringify({ region_id: regionId, action }),
  });
}

export async function batchRegionAction(
  docId: string,
  regionIds: string[],
  action: RegionAction
): Promise<void> {
  await request(`/api/documents/${docId}/regions/batch-action`, {
    method: "PUT",
    body: JSON.stringify({ region_ids: regionIds, action }),
  });
}

export async function addManualRegion(
  docId: string,
  region: Partial<PIIRegion>
): Promise<{ status: string; region_id: string }> {
  return request(`/api/documents/${docId}/regions/add`, {
    method: "POST",
    body: JSON.stringify(region),
  });
}

export async function updateRegionBBox(
  docId: string,
  regionId: string,
  bbox: BBox,
): Promise<void> {
  await request(`/api/documents/${docId}/regions/${regionId}/bbox`, {
    method: "PUT",
    body: JSON.stringify(bbox),
  });
}

export async function reanalyzeRegion(
  docId: string,
  regionId: string,
): Promise<{ region_id: string; text: string; pii_type: string; confidence: number; source: string }> {
  return request(`/api/documents/${docId}/regions/${regionId}/reanalyze`, {
    method: "POST",
  });
}

export async function updateRegionLabel(
  docId: string,
  regionId: string,
  piiType: string,
): Promise<void> {
  await request(`/api/documents/${docId}/regions/${regionId}/label`, {
    method: "PUT",
    body: JSON.stringify({ pii_type: piiType }),
  });
}

export async function updateRegionText(
  docId: string,
  regionId: string,
  text: string,
): Promise<void> {
  await request(`/api/documents/${docId}/regions/${regionId}/text`, {
    method: "PUT",
    body: JSON.stringify({ text }),
  });
}

export async function highlightAllRegions(
  docId: string,
  regionId: string,
): Promise<{ created: number; new_regions: PIIRegion[]; all_ids: string[] }> {
  return request(`/api/documents/${docId}/regions/highlight-all`, {
    method: "POST",
    body: JSON.stringify({ region_id: regionId }),
  });
}

// ──────────────────────────────────────────────
// Anonymization
// ──────────────────────────────────────────────

export async function syncRegions(
  docId: string,
  regions: Array<{ id: string; action: string; bbox: BBox }>,
): Promise<void> {
  await request(`/api/documents/${docId}/regions/sync`, {
    method: "PUT",
    body: JSON.stringify(regions),
  });
}

export async function anonymizeDocument(
  docId: string
): Promise<AnonymizeResponse> {
  return request<AnonymizeResponse>(`/api/documents/${docId}/anonymize`, {
    method: "POST",
  });
}

export function getDownloadUrl(docId: string, fileType: "pdf" | "text"): string {
  return `${BASE_URL}/api/documents/${docId}/download/${fileType}`;
}

// ──────────────────────────────────────────────
// De-tokenization
// ──────────────────────────────────────────────

export async function detokenize(text: string): Promise<DetokenizeResponse> {
  return request<DetokenizeResponse>("/api/detokenize", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export interface DetokenizeFileResult {
  blob: Blob;
  filename: string;
  tokensReplaced: number;
  unresolvedTokens: string[];
}

export async function detokenizeFile(file: File): Promise<DetokenizeFileResult> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${BASE_URL}/api/detokenize/file`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Server error ${res.status}`);
  }

  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : file.name.replace(/\.(\w+)$/, "_detokenized.$1");

  const tokensReplaced = parseInt(res.headers.get("X-Tokens-Replaced") || "0", 10);
  const unresolvedRaw = res.headers.get("X-Unresolved-Tokens") || "";
  const unresolvedTokens = unresolvedRaw ? unresolvedRaw.split(",") : [];

  const blob = await res.blob();
  return { blob, filename, tokensReplaced, unresolvedTokens };
}

// ──────────────────────────────────────────────
// Vault
// ──────────────────────────────────────────────

export async function unlockVault(passphrase: string): Promise<void> {
  await request("/api/vault/unlock", {
    method: "POST",
    body: JSON.stringify({ passphrase }),
  });
}

export async function getVaultStatus(): Promise<{ unlocked: boolean; path: string }> {
  return request("/api/vault/status");
}

export async function getVaultStats(): Promise<VaultStats> {
  return request<VaultStats>("/api/vault/stats");
}

export async function listVaultTokens(
  sourceDocument?: string
): Promise<TokenMapping[]> {
  const params = sourceDocument ? `?source_document=${encodeURIComponent(sourceDocument)}` : "";
  return request<TokenMapping[]>(`/api/vault/tokens${params}`);
}

// ──────────────────────────────────────────────
// LLM
// ──────────────────────────────────────────────

export async function getLLMStatus(): Promise<LLMStatus> {
  return request<LLMStatus>("/api/llm/status");
}

export async function loadLLM(
  modelPath: string,
  forceCpu = false
): Promise<void> {
  await request(
    `/api/llm/load?model_path=${encodeURIComponent(modelPath)}&force_cpu=${forceCpu}`,
    { method: "POST" }
  );
}

export async function unloadLLM(): Promise<void> {
  await request("/api/llm/unload", { method: "POST" });
}

export async function listModels(): Promise<
  Array<{ name: string; path: string; size_gb: number }>
> {
  return request("/api/llm/models");
}

// ──────────────────────────────────────────────
// Health
// ──────────────────────────────────────────────

export async function checkHealth(): Promise<boolean> {
  try {
    await request("/health");
    return true;
  } catch {
    return false;
  }
}

// ──────────────────────────────────────────────
// Settings
// ──────────────────────────────────────────────

export async function getSettings(): Promise<Record<string, unknown>> {
  return request("/api/settings");
}

export async function updateSettings(
  updates: Record<string, unknown>
): Promise<{ status: string; applied: Record<string, unknown> }> {
  return request("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(updates),
  });
}

// ──────────────────────────────────────────────
// Vault export
// ──────────────────────────────────────────────

export async function exportVault(passphrase: string): Promise<string> {
  const res = await request<{ export: string }>(
    `/api/vault/export?passphrase=${encodeURIComponent(passphrase)}`,
    { method: "POST" }
  );
  return res.export;
}
