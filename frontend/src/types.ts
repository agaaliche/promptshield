/** Type definitions matching the Python backend models. */

export type PIIType =
  | "PERSON" | "ORG" | "EMAIL" | "PHONE" | "SSN"
  | "CREDIT_CARD" | "DATE" | "ADDRESS" | "LOCATION"
  | "IP_ADDRESS" | "IBAN" | "PASSPORT" | "DRIVER_LICENSE"
  | "CUSTOM" | "UNKNOWN"
  | (string & {});  // allow arbitrary user-defined labels

export type DetectionSource = "REGEX" | "NER" | "GLINER" | "LLM" | "MANUAL";
export type RegionAction = "PENDING" | "CANCEL" | "REMOVE" | "TOKENIZE";
export type DocumentStatus =
  | "UPLOADING" | "PROCESSING" | "DETECTING"
  | "REVIEWING" | "ANONYMIZING" | "COMPLETED" | "ERROR";

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface TextBlock {
  text: string;
  bbox: BBox;
  confidence: number;
  block_index: number;
  line_index: number;
  word_index: number;
  is_ocr: boolean;
}

export interface PageData {
  page_number: number;
  width: number;
  height: number;
  bitmap_path: string;
  text_blocks: TextBlock[];
  full_text: string;
}

export interface PIIRegion {
  id: string;
  page_number: number;
  bbox: BBox;
  text: string;
  pii_type: PIIType;
  confidence: number;
  source: DetectionSource;
  char_start: number;
  char_end: number;
  action: RegionAction;
}

export interface DocumentInfo {
  doc_id: string;
  original_filename: string;
  file_path: string;
  mime_type: string;
  page_count: number;
  status: DocumentStatus;
  pages: PageData[];
  regions: PIIRegion[];
  is_protected?: boolean;
  created_at: string;
}

export interface UploadResponse {
  doc_id: string;
  filename: string;
  page_count: number;
  status: DocumentStatus;
}

export interface DetectionResult {
  doc_id: string;
  total_regions: number;
  regions: PIIRegion[];
}

export interface DetectionProgressPageStatus {
  page: number;
  status: "pending" | "running" | "done";
  regions: number;
}

export interface DetectionProgressData {
  doc_id: string;
  status: "idle" | "running" | "complete" | "error";
  current_page: number;
  total_pages: number;
  pages_done: number;
  regions_found: number;
  elapsed_seconds: number;
  page_statuses: DetectionProgressPageStatus[];
  error?: string;
}

export interface RedetectResult {
  doc_id: string;
  added: number;
  updated: number;
  total_regions: number;
  regions: PIIRegion[];
}

export interface AnonymizeResponse {
  doc_id: string;
  output_path: string | null;
  output_text_path: string | null;
  tokens_created: number;
  regions_removed: number;
}

export interface DetokenizeResponse {
  original_text: string;
  tokens_replaced: number;
  unresolved_tokens: string[];
}

export interface LLMStatus {
  loaded: boolean;
  model_name: string;
  model_path: string;
  gpu_enabled: boolean;
  context_size: number;
  provider: "local" | "remote";
  remote_api_url: string;
  remote_model: string;
}

export interface VaultStats {
  total_tokens: number;
  total_documents: number;
  vault_size_bytes: number;
}

export interface TokenMapping {
  token_id: string;
  token_string: string;
  original_text: string;
  pii_type: PIIType;
  source_document: string;
  context_snippet: string;
  created_at: string;
}

/** Color map for PII type badges */
export const PII_COLORS: Record<string, string> = {
  PERSON: "#e91e63",
  ORG: "#ff5722",
  EMAIL: "#2196f3",
  PHONE: "#00bcd4",
  SSN: "#f44336",
  CREDIT_CARD: "#ff9800",
  DATE: "#8bc34a",
  ADDRESS: "#795548",
  LOCATION: "#607d8b",
  IP_ADDRESS: "#9e9e9e",
  IBAN: "#ff5722",
  PASSPORT: "#673ab7",
  DRIVER_LICENSE: "#3f51b5",
  CUSTOM: "#9c27b0",
  UNKNOWN: "#757575",
};

/** Get color for a PII type, with fallback for user-defined labels */
export function getPIIColor(type: string): string {
  return PII_COLORS[type] || "#888";
}

/** Built-in PII type labels */
export const BUILTIN_PII_TYPES: PIIType[] = [
  "PERSON", "ORG", "EMAIL", "PHONE", "SSN",
  "CREDIT_CARD", "DATE", "ADDRESS", "LOCATION",
  "IP_ADDRESS", "IBAN", "PASSPORT", "DRIVER_LICENSE",
  "CUSTOM", "UNKNOWN",
];

/** Configuration for a PII label in the type picker */
export interface PIILabelEntry {
  label: PIIType;
  frequent: boolean;
  hidden: boolean;
  userAdded: boolean;
  color: string;
}

const LABEL_CONFIG_KEY = "piiLabelConfig";

/** Ensure all built-in types are present in a label config array */
export function ensureBuiltinLabels(entries: PIILabelEntry[]): PIILabelEntry[] {
  const existing = new Set(entries.map((e) => e.label));
  for (const t of BUILTIN_PII_TYPES) {
    if (!existing.has(t)) {
      entries.push({
        label: t,
        frequent: ["PERSON", "ORG", "EMAIL", "PHONE", "DATE", "ADDRESS"].includes(t),
        hidden: false,
        userAdded: false,
        color: PII_COLORS[t] || "#888",
      });
    }
  }
  return entries;
}

/** Load label config from localStorage cache (sync, for initial render) */
export function loadLabelConfig(): PIILabelEntry[] {
  let saved: PIILabelEntry[] = [];
  try {
    const raw = localStorage.getItem(LABEL_CONFIG_KEY);
    if (raw) saved = JSON.parse(raw);
  } catch { /* ignore */ }
  return ensureBuiltinLabels(saved);
}

/** Save label config to localStorage cache */
export function cacheLabelConfig(config: PIILabelEntry[]): void {
  try {
    localStorage.setItem(LABEL_CONFIG_KEY, JSON.stringify(config));
  } catch { /* ignore */ }
}

/** @deprecated Use cacheLabelConfig + saveLabelConfigAPI instead */
export const saveLabelConfig = cacheLabelConfig;

export interface UploadItem {
  id: string;
  name: string;
  parentPath: string;
  status: "queued" | "uploading" | "detecting" | "done" | "error";
  progress: number;
  error?: string;
}

export interface SnackbarItem {
  id: string;
  message: string;
  type: "success" | "error" | "info";
  createdAt: number;
}
