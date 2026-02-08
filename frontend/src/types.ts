/** Type definitions matching the Python backend models. */

export type PIIType =
  | "PERSON" | "ORG" | "EMAIL" | "PHONE" | "SSN"
  | "CREDIT_CARD" | "DATE" | "ADDRESS" | "LOCATION"
  | "IP_ADDRESS" | "IBAN" | "PASSPORT" | "DRIVER_LICENSE"
  | "CUSTOM" | "UNKNOWN";

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

export interface AnonymizeResponse {
  doc_id: string;
  output_pdf_path: string | null;
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
export const PII_COLORS: Record<PIIType, string> = {
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
