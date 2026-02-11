/** API client for communicating with the Python sidecar backend. */

import type {
  AnonymizeResponse,
  BBox,
  DetectionProgressData,
  DetectionResult,
  DetokenizeResponse,
  DocumentInfo,
  LLMStatus,
  PIILabelEntry,
  PIIRegion,
  RedetectResult,
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

/** Fire-and-forget error handler — logs to console instead of silently swallowing. */
export function logError(context: string) {
  return (err: unknown) => {
    if (err instanceof DOMException && err.name === "AbortError") return; // expected on cancel
    console.error(`[${context}]`, err);
  };
}

/** Active AbortControllers — cancel all in-flight requests. */
const _activeControllers = new Set<AbortController>();
let _globalAbort: AbortController | null = null;

/** Cancel all pending API requests (e.g. on doc switch). */
export function cancelAllRequests(): void {
  for (const ctrl of _activeControllers) {
    ctrl.abort();
  }
  _activeControllers.clear();
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  /** Pass a custom signal to override the default per-request one. */
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  _activeControllers.add(controller);
  const url = `${BASE_URL}${path}`;
  // M17: Extract headers from options separately, then spread options first
  // so that our signal and headers always take precedence.
  const { headers: optHeaders, signal: _discardedSignal, ...restOptions } = options;
  try {
    const res = await fetch(url, {
      ...restOptions,
      headers: { "Content-Type": "application/json", ...optHeaders as Record<string, string> },
      signal: signal ?? controller.signal,
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API error ${res.status}: ${body}`);
    }

    return res.json();
  } finally {
    _activeControllers.delete(controller);
  }
}

// ──────────────────────────────────────────────
// Documents
// ──────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<UploadResponse> {
  if (!_globalAbort) _globalAbort = new AbortController();
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
    signal: _globalAbort.signal,
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

export async function deleteDocument(docId: string): Promise<void> {
  await request(`/api/documents/${docId}`, { method: "DELETE" });
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

export async function getDetectionProgress(docId: string): Promise<DetectionProgressData> {
  return request<DetectionProgressData>(`/api/documents/${docId}/detection-progress`);
}

export async function redetectPII(
  docId: string,
  options: {
    confidence_threshold?: number;
    page_number?: number | null;
    regex_enabled?: boolean;
    ner_enabled?: boolean;
    llm_detection_enabled?: boolean;
    regex_types?: string[] | null;
    ner_types?: string[] | null;
  } = {}
): Promise<RedetectResult> {
  return request<RedetectResult>(`/api/documents/${docId}/redetect`, {
    method: "POST",
    body: JSON.stringify(options),
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

export async function deleteRegion(
  docId: string,
  regionId: string,
): Promise<void> {
  await request(`/api/documents/${docId}/regions/${regionId}`, {
    method: "DELETE",
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

export async function batchDeleteRegions(
  docId: string,
  regionIds: string[],
): Promise<void> {
  await request(`/api/documents/${docId}/regions/batch-delete`, {
    method: "POST",
    body: JSON.stringify({ region_ids: regionIds, action: "CANCEL" }),
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

/**
 * Batch-anonymize multiple documents.
 * Returns a blob URL — caller MUST call URL.revokeObjectURL() after use.
 */
export async function batchAnonymize(docIds: string[]): Promise<string> {
  if (!_globalAbort) _globalAbort = new AbortController();
  const resp = await fetch(`${BASE_URL}/api/documents/batch-anonymize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_ids: docIds }),
    signal: _globalAbort.signal,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Batch anonymize failed (${resp.status})`);
  }
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
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

  if (!_globalAbort) _globalAbort = new AbortController();
  const res = await fetch(`${BASE_URL}/api/detokenize/file`, {
    method: "POST",
    body: form,
    signal: _globalAbort.signal,
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

export async function configureRemoteLLM(
  apiUrl: string,
  apiKey: string,
  model: string
): Promise<void> {
  await request("/api/llm/remote/configure", {
    method: "POST",
    body: JSON.stringify({ api_url: apiUrl, api_key: apiKey, model }),
  });
}

export async function disconnectRemoteLLM(): Promise<void> {
  await request("/api/llm/remote/disconnect", { method: "POST" });
}

export async function testRemoteLLM(): Promise<{
  ok: boolean;
  latency_ms?: number;
  model?: string;
  response?: string;
  error?: string;
}> {
  return request("/api/llm/remote/test", { method: "POST" });
}

export async function setLLMProvider(
  provider: "local" | "remote"
): Promise<void> {
  await request(`/api/llm/provider?provider=${provider}`, { method: "POST" });
}

export async function listModels(): Promise<
  Array<{ name: string; path: string; size_gb: number }>
> {
  return request("/api/llm/models");
}

export async function openModelsDir(): Promise<{ status: string; path: string }> {
  return request("/api/llm/open-models-dir", { method: "POST" });
}

// ──────────────────────────────────────────────
// System hardware
// ──────────────────────────────────────────────

export interface HardwareInfo {
  cpu: { name: string; cores_physical: number; cores_logical: number };
  ram: { total_gb: number; available_gb: number };
  gpus: Array<{
    name: string;
    vram_total_mb: number;
    vram_free_mb: number;
    driver_version: string;
  }>;
}

export async function getHardwareInfo(): Promise<HardwareInfo> {
  return request("/api/system/hardware");
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
    `/api/vault/export`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passphrase }),
    }
  );
  return res.export;
}

export async function importVault(
  exportData: string,
  passphrase: string
): Promise<{ imported: number; skipped: number; errors: number }> {
  return request(`/api/vault/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ export_data: exportData, passphrase }),
  });
}

// ──────────────────────────────────────────────
// PII Label configuration
// ──────────────────────────────────────────────

export async function fetchLabelConfig(): Promise<PIILabelEntry[]> {
  return request<PIILabelEntry[]>("/api/settings/labels");
}

export async function saveLabelConfigAPI(labels: PIILabelEntry[]): Promise<void> {
  await request("/api/settings/labels", {
    method: "PUT",
    body: JSON.stringify(labels),
  });
}
