# Backend Python Codebase Audit Report

**Project:** doc-anonymizer (promptShield)  
**Scope:** `src-python/` — FastAPI backend sidecar  
**Date:** 2025-01-XX  
**Audited by:** Automated code review (all files read end-to-end)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Inventory & Size Map](#2-file-inventory--size-map)
3. [Per-Module Quality Analysis](#3-per-module-quality-analysis)
4. [API Endpoint Catalogue](#4-api-endpoint-catalogue)
5. [Dependency Inventory](#5-dependency-inventory)
6. [Hardcoded Secrets & Security](#6-hardcoded-secrets--security)
7. [Test Coverage Assessment](#7-test-coverage-assessment)
8. [Summary of Findings](#8-summary-of-findings)

---

## 1. Architecture Overview

A **local-only FastAPI sidecar** embedded in a Tauri desktop app for PII detection and document anonymization.

```
main.py                     Entry point — starts uvicorn, finds free port
├── api/
│   ├── server.py            FastAPI app, CORS, lifespan, SPA fallback
│   ├── deps.py              Shared state: documents dict, store, locks
│   ├── rate_limit.py        Sliding-window rate limiter
│   └── routers/
│       ├── documents.py     Upload, list, get, delete
│       ├── detection.py     detect_pii, redetect, reset, progress
│       ├── regions.py       CRUD, batch ops, blacklist search, highlight-all
│       ├── anonymize.py     Anonymize + download
│       ├── detokenize.py    Text & file de-tokenization
│       ├── vault.py         Unlock, status, tokens, export/import
│       ├── llm.py           LLM load/unload, remote config, provider switch
│       └── settings.py      Config CRUD, label config, GPU info
├── models/
│   └── schemas.py           Pydantic v2 models (14 PII types, 5 sources)
└── core/
    ├── config.py            AppConfig with JSON persistence
    ├── detection/
    │   ├── pipeline.py      Orchestrator: Regex → NER → GLiNER → LLM
    │   ├── regex_detector.py Pattern matching with validation
    │   ├── regex_patterns.py Declarative multi-language patterns
    │   ├── ner_detector.py   spaCy NER with model cascade
    │   ├── bert_detector.py  HuggingFace BERT NER (5 models)
    │   ├── gliner_detector.py Zero-shot GLiNER NER
    │   ├── llm_detector.py   LLM-based detection with sliding window
    │   ├── merge.py          Cross-layer merge, confidence boosting
    │   ├── noise_filters.py  200+ noise terms for false-positive suppression
    │   ├── block_offsets.py  Char offset ↔ TextBlock mapping
    │   ├── region_shapes.py  Shape constraints (word/line limits)
    │   ├── cross_line.py     Cross-line ORG boundary detection
    │   ├── propagation.py    Cross-page region propagation
    │   └── language.py       Stop-word language detection (6 languages)
    ├── anonymizer/
    │   └── engine.py         PDF/DOCX/XLSX/image anonymization + metadata scrub
    ├── ingestion/
    │   └── loader.py         PDF text extraction, OCR fallback, Office convert
    ├── llm/
    │   ├── engine.py         llama-cpp-python local LLM wrapper
    │   └── remote_engine.py  OpenAI-compatible remote LLM (httpx)
    ├── ocr/
    │   └── engine.py         Tesseract OCR integration
    ├── persistence/
    │   └── store.py          Document state persistence (JSON + atomic writes)
    ├── vault/
    │   └── store.py          SQLite vault with Fernet field-level encryption
    └── detokenize_file.py    PDF/DOCX/XLSX/TXT de-tokenization
```

**Total:** ~40 Python files, ~13,000+ lines of production code + ~2,700 lines of tests.

---

## 2. File Inventory & Size Map

### Production Code (by size)

| File | Lines | Complexity |
|------|------:|:----------:|
| `core/detection/ner_detector.py` | 981 | HIGH |
| `core/anonymizer/engine.py` | 898 | HIGH |
| `core/detection/regex_patterns.py` | 876 | MEDIUM |
| `api/routers/regions.py` | 662 | HIGH |
| `core/detection/bert_detector.py` | 624 | MEDIUM |
| `core/ingestion/loader.py` | 593 | HIGH |
| `core/detection/merge.py` | 585 | HIGH |
| `core/detection/pipeline.py` | 500 | HIGH |
| `core/vault/store.py` | 505 | MEDIUM |
| `api/routers/detection.py` | ~500 | HIGH |
| `core/detection/regex_detector.py` | ~500 | MEDIUM |
| `core/detection/noise_filters.py` | 424 | LOW |
| `core/detection/block_offsets.py` | ~400 | HIGH |
| `core/persistence/store.py` | 331 | LOW |
| `core/detokenize_file.py` | 318 | MEDIUM |
| `api/server.py` | 321 | MEDIUM |
| `core/detection/llm_detector.py` | 312 | MEDIUM |
| `core/detection/region_shapes.py` | ~300 | MEDIUM |
| `core/detection/propagation.py` | ~180 | LOW |
| `core/llm/engine.py` | ~250 | LOW |
| `core/llm/remote_engine.py` | 234 | LOW |
| `models/schemas.py` | 243 | LOW |
| `api/routers/settings.py` | 228 | LOW |
| `core/detection/language.py` | ~200 | LOW |
| `api/deps.py` | 191 | MEDIUM |
| `core/config.py` | 185 | LOW |
| `api/routers/anonymize.py` | ~170 | LOW |
| `api/routers/vault.py` | ~170 | MEDIUM |
| `api/routers/llm.py` | ~170 | LOW |
| `api/routers/documents.py` | ~170 | LOW |
| `core/detection/cross_line.py` | ~120 | LOW |
| `core/ocr/engine.py` | ~120 | LOW |
| `api/rate_limit.py` | 103 | LOW |
| `api/routers/detokenize.py` | ~100 | LOW |
| `main.py` | 89 | LOW |
| `core/detection/bbox_utils.py` | 76 | LOW |
| `core/detection/gliner_detector.py` | 395 | MEDIUM |

### Test Code

| File | Lines | Modules Covered |
|------|------:|:----------------|
| `tests/test_regex_detector.py` | 655 | regex_detector |
| `tests/test_regex_bulletproof.py` | 549 | regex_detector (edge cases) |
| `tests/test_region_shapes.py` | 452 | region_shapes, pipeline |
| `tests/test_anonymizer_engine.py` | 423 | anonymizer/engine |
| `tests/test_italian.py` | 344 | Italian language support |
| `tests/test_offset_alignment.py` | 299 | block_offsets, loader |
| `tests/test_routers.py` | 269 | All API routers |
| `tests/test_vault.py` | ~100 | vault/store |
| `tests/test_detokenize_file.py` | ~100 | detokenize_file |
| `tests/test_ner_detector.py` | ~50 | ner_detector |

---

## 3. Per-Module Quality Analysis

### 3.1 `main.py` — Entry Point
**Rating: GOOD**
- Clean entry point, proper port selection with retry logic
- Handles frozen (PyInstaller) mode correctly
- Prints `PORT:XXXX` for Tauri sidecar IPC
- Minor: Uses `signal.signal(SIGTERM)` for cleanup — good practice
- No issues found

### 3.2 `api/server.py` — FastAPI Application
**Rating: GOOD**
- Proper `lifespan` context manager for startup/shutdown
- CORS restricted to `localhost:1420`, `localhost:5173`, `tauri://localhost` — correct for desktop app
- Rate limiting middleware (600 req/60s) with path exemptions
- SPA fallback for frontend serving
- Auto-loads documents from persistent store on startup
- Clears stale detection regions on startup — good resilience
- Model warmup endpoint for cold-start optimization
- **Minor concern:** Static file mount path is `bin/frontend-dist` relative — could be fragile in different deployment modes

### 3.3 `api/deps.py` — Shared State
**Rating: FAIR** 
- Global mutable `documents: dict[str, DocumentInfo]` — appropriate for single-user desktop app
- Global `store` singleton — initialized lazily
- `config_override` context manager protects config mutations under detection lock
- **Concern:** `detection_lock` is an `asyncio.Lock` with 10-minute timeout, but detection uses `threading.Lock` in the router — dual-lock pattern could deadlock in edge cases
- **Concern:** `_stale_progress` dict grows unbounded; only cleaned on startup

### 3.4 `api/rate_limit.py` — Rate Limiting
**Rating: GOOD**
- Sliding window algorithm (deque of timestamps)
- Exempts health, bitmap, and polling endpoints
- 600 requests per 60 seconds — generous but appropriate for desktop
- Returns 429 with `Retry-After` header — standards-compliant

### 3.5 `api/routers/documents.py` — Document Upload
**Rating: GOOD**
- 200 MB upload size limit with validation
- Path traversal protection: strips directory components, blocks `..`
- MIME type guessing + extension validation
- Temporary file cleanup in error path
- Saves to persistent store after processing

### 3.6 `api/routers/detection.py` — PII Detection
**Rating: FAIR**
- Core detection orchestration with progress tracking
- `asyncio.to_thread()` for CPU-bound detection work — correct
- **Concern:** ~500 lines — detection, redetection, reset, and progress are all in one file with duplicated detection logic between `detect_pii` and `redetect_pii`
- **Concern:** Blacklist search logic duplicated between detection.py and regions.py
- Progress dict cleanup relies on timestamps and startup sweep

### 3.7 `api/routers/regions.py` — Region Management
**Rating: FAIR**
- Comprehensive CRUD operations for PII regions
- Blacklist search with case-insensitive matching and overlap detection
- Highlight-all with fuzzy matching (difflib `SequenceMatcher`)
- **Concern:** 662 lines — largest router; highlight-all alone is ~200 lines of complex fuzzy matching and Unicode normalization
- **Concern:** The fuzzy sliding-window search in `_highlight_all_impl` is O(n*m) and could be slow on large documents
- **Concern:** `_normalize()` and `_fuzzy_ratio()` are defined as module-level helpers but similar logic exists in other modules

### 3.8 `api/routers/anonymize.py` — Anonymization
**Rating: GOOD**
- Region sync before anonymization
- Batch anonymize with ZIP download
- Proper content-disposition headers
- Temp file cleanup

### 3.9 `api/routers/vault.py` — Token Vault API
**Rating: GOOD**
- Rate limiting on unlock attempts (5 attempts / 60s lockout) — brute-force protection
- Pagination for token listing
- Export/import with separate encryption passphrase
- Proper error handling for locked vault state (403)

### 3.10 `api/routers/llm.py` — LLM Management
**Rating: GOOD**
- Path validation: model must be under `models_dir`, must be `.gguf`
- `resolve().relative_to()` prevents path traversal
- Provider switching (local/remote)
- Remote LLM configuration with URL/key/model
- `open-models-dir` uses `os.startfile` / `subprocess` — desktop-appropriate

### 3.11 `api/routers/settings.py` — Settings
**Rating: GOOD**
- Pydantic-validated PATCH endpoint — safely applies only known fields
- PII label config CRUD with per-label defaults
- GPU info via `nvidia-smi` subprocess
- API key masked in settings response (shows `"...key_present..."`) — good security practice

### 3.12 `models/schemas.py` — Data Models
**Rating: EXCELLENT**
- Clean Pydantic v2 models with proper validation
- 14 PII types, 5 detection sources, 3 region actions
- `PIIRegion` has `linked_group` for multi-part entity linking
- `uuid4().hex[:12]` for IDs — sufficient uniqueness for local use
- All fields have sensible defaults

### 3.13 `core/config.py` — Configuration
**Rating: GOOD**
- Pydantic `BaseModel` with field validators
- Persists user settings to JSON sidecar file
- API key sourced from `DOC_ANON_LLM_API_KEY` env var — no hardcoded keys
- Sensible defaults for all parameters
- `_save_user_settings()` filters to user-tweakable fields only

### 3.14 `core/detection/pipeline.py` — Detection Orchestrator
**Rating: GOOD**
- Clean layered architecture: Regex → NER → GLiNER → LLM
- Per-type filtering with `excluded_types` set
- Language detection drives NER model selection
- Timing metrics for each detection layer
- Re-exports symbols from submodules for backward compatibility
- `reanalyze_bbox()` for single-region re-evaluation

### 3.15 `core/detection/merge.py` — Detection Merge
**Rating: GOOD (complex by necessity)**
- Cross-layer confidence boosting (+0.10 for 2 layers, +0.15 for 3)
- Overlap resolution by confidence (higher wins, lower clipped)
- ADDRESS fragment merging for multi-word addresses
- Per-line bbox generation with spatial grouping
- Shape enforcement delegates to `region_shapes.py`
- **Note:** 585 lines, but the complexity is inherent to the multi-layer merge problem

### 3.16 `core/detection/regex_detector.py` — Regex PII
**Rating: GOOD**
- Validation functions: Luhn (credit card), IBAN mod-97, French SSN, Dutch BSN, Portuguese NIF
- Context keyword boosting (e.g., "SSN:" near pattern → +confidence)
- Exclusion patterns prevent common false positives
- Overlap resolution: longer match wins

### 3.17 `core/detection/ner_detector.py` — spaCy NER
**Rating: FAIR**
- 981 lines — largest single file
- Model cascade: trf → lg → sm with automatic selection
- Language detection heuristics for Italian/French
- Chunking for documents > 100k characters
- Extensive false-positive filtering
- **Concern:** Heuristic name detection regex is complex and language-specific
- **Concern:** Italian text detection (`_is_italian_text`) duplicates logic in `language.py`

### 3.18 `core/detection/bert_detector.py` — BERT NER
**Rating: GOOD**
- 5 supported models with label mappings
- Token aggregation (`simple` strategy)
- False-positive noise filtering via `noise_filters.py`
- Graceful handling of model loading failures

### 3.19 `core/detection/gliner_detector.py` — GLiNER
**Rating: GOOD**
- Zero-shot multilingual NER
- Extensive false-positive filtering (URLs, file extensions, common words)
- Confidence scaling per entity type

### 3.20 `core/detection/llm_detector.py` — LLM Detection
**Rating: GOOD**
- Sliding-window chunking to fit context limits
- JSON output parsing with robust error handling
- Fuzzy substring matching for found entities → exact bbox positions
- Works with both local and remote LLM engines

### 3.21 `core/anonymizer/engine.py` — Anonymization Engine
**Rating: GOOD**
- Multi-format support: PDF, DOCX, XLSX, images
- **PDF:** Erase-then-insert approach preserving font style + baseline
- **DOCX:** Cross-run replacement preserving formatting (handles PII split across XML runs)
- **XLSX:** Cell-by-cell replacement including comments
- **Images:** Bitmap manipulation with font sizing
- **Metadata scrubbing:** Strips all metadata (EXIF, XMP, author, TOC, annotations, attachments)
- Linked groups share a single token — correct de-duplication
- Token manifest saved encrypted via vault Fernet
- **Minor concern:** `_replace_in_docx_xml_parts` accesses internal `part._blob` — fragile coupling to python-docx internals

### 3.22 `core/ingestion/loader.py` — Document Ingestion
**Rating: GOOD**
- PDF text extraction via pypdfium2 with character-level bounding boxes
- Rotated text detection and filtering (watermarks)
- OCR fallback for scanned pages (< 20 chars extracted)
- Image upscaling for small images before OCR
- Office document conversion: XLSX via pure-Python (openpyxl+reportlab), others via LibreOffice
- Line clustering algorithm handles noisy y-coordinates from OCR
- **Minor concern:** `_xlsx_to_pdf` truncates cells at 100 chars and limits to 500 rows — could lose data

### 3.23 `core/llm/engine.py` — Local LLM Engine
**Rating: GOOD**
- Thread-safe with `threading.Lock` (llama.cpp is not thread-safe)
- Memory check before model loading
- Graceful fallback: chat → merged prompt → plain completion
- Singleton pattern appropriate for single-user desktop app

### 3.24 `core/llm/remote_engine.py` — Remote LLM Engine
**Rating: GOOD**
- `httpx.Client` with connection pooling
- Retry with exponential backoff (3 retries)
- Handles 429 rate-limit and 5xx errors
- `test_connection()` latency check
- Identical API to local engine for transparent swapping

### 3.25 `core/ocr/engine.py` — OCR Engine
**Rating: GOOD**
- Tesseract availability check with common Windows paths
- Confidence threshold at 30% to reduce garbage
- Coordinate scaling from pixel to page coordinates
- Clean separation from main ingestion pipeline

### 3.26 `core/persistence/store.py` — Document Store
**Rating: GOOD**
- Atomic writes via `tempfile.mkstemp` + `os.replace`
- Path traversal protection: `_validate_doc_id`, `_sanitize_filename`
- PII label config persistence
- `load_all_documents()` for startup restoration

### 3.27 `core/vault/store.py` — Token Vault
**Rating: EXCELLENT**
- **Encryption:** PBKDF2 with SHA-256 (480,000 iterations) + Fernet field-level encryption
- Passphrase verification via stored encrypted token
- SQLite with WAL journal mode for concurrent reads
- Thread-safe with `threading.Lock`
- Compact tokens `[P38291]` — 8 chars, 100k unique per type
- Export/import with separate encryption key
- **Well-designed security model** for a local desktop app

### 3.28 `core/detokenize_file.py` — File De-tokenization
**Rating: GOOD**
- Multi-format: PDF, DOCX, XLSX, TXT/CSV
- PDF: visual style preservation (font, size, color, baseline)
- Rejects legacy `.doc` and `.xls` formats with helpful message
- Delegates style extraction to anonymizer engine (reuse)

---

## 4. API Endpoint Catalogue

### Health & System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/warmup` | Model warmup (cold start) |

### Documents
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/upload` | Upload document (200MB limit) |
| GET | `/api/documents` | List all documents |
| GET | `/api/documents/{doc_id}` | Get document metadata |
| GET | `/api/documents/{doc_id}/pages/{page}/bitmap` | Serve page bitmap |
| DELETE | `/api/documents/{doc_id}` | Delete document |

### Detection
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/{doc_id}/detect` | Run full PII detection |
| POST | `/api/documents/{doc_id}/redetect` | Re-detect with filters/blacklist |
| POST | `/api/documents/{doc_id}/reset-detection` | Clear all detections |
| GET | `/api/documents/{doc_id}/regions` | Get detected regions |
| GET | `/api/documents/{doc_id}/detection-progress` | Poll progress |

### Regions
| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/documents/{doc_id}/regions/{region_id}/action` | Set region action |
| POST | `/api/documents/{doc_id}/regions/batch-action` | Batch set actions |
| PUT | `/api/documents/{doc_id}/regions/{region_id}/bbox` | Update bbox |
| PUT | `/api/documents/{doc_id}/regions/{region_id}/label` | Update PII label |
| PUT | `/api/documents/{doc_id}/regions/{region_id}/text` | Update text |
| POST | `/api/documents/{doc_id}/regions/{region_id}/reanalyze` | Re-analyze region |
| POST | `/api/documents/{doc_id}/regions/add` | Add manual region |
| POST | `/api/documents/{doc_id}/regions/blacklist-search` | Blacklist search |
| POST | `/api/documents/{doc_id}/regions/highlight-all` | Find all occurrences |

### Anonymization
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/{doc_id}/regions/sync` | Sync regions before anon |
| POST | `/api/documents/{doc_id}/anonymize` | Anonymize single doc |
| POST | `/api/anonymize/batch` | Batch anonymize |
| GET | `/api/documents/{doc_id}/download/{output_type}` | Download output |
| POST | `/api/export/zip` | Export multiple as ZIP |

### De-tokenization
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/detokenize` | De-tokenize text string |
| POST | `/api/detokenize/file` | De-tokenize uploaded file |

### Vault
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/vault/unlock` | Unlock vault with passphrase |
| GET | `/api/vault/status` | Vault lock status |
| GET | `/api/vault/stats` | Token/document counts |
| GET | `/api/vault/tokens` | List tokens (paginated) |
| POST | `/api/vault/export` | Export vault (encrypted) |
| POST | `/api/vault/import` | Import vault backup |

### LLM
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/llm/status` | LLM status (loaded, model, provider) |
| POST | `/api/llm/load` | Load local GGUF model |
| POST | `/api/llm/unload` | Unload model |
| GET | `/api/llm/models` | List available .gguf files |
| POST | `/api/llm/remote/configure` | Configure remote LLM |
| POST | `/api/llm/remote/disconnect` | Disconnect remote |
| POST | `/api/llm/remote/test` | Test remote connection |
| POST | `/api/llm/provider` | Switch local/remote |
| POST | `/api/llm/open-models-dir` | Open models directory in OS |

### Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get all settings |
| PATCH | `/api/settings` | Update settings |
| GET | `/api/settings/labels` | Get PII label config |
| PUT | `/api/settings/labels` | Set PII label config |
| GET | `/api/settings/gpu` | Get GPU info (nvidia-smi) |

**Total: 37 endpoints**

---

## 5. Dependency Inventory

### Runtime Dependencies

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `fastapi` | >=0.115.0 | Web framework |
| `uvicorn[standard]` | >=0.34.0 | ASGI server |
| `pypdfium2` | >=4.30.0 | PDF text extraction |
| `Pillow` | >=11.0.0 | Image processing |
| `pytesseract` | >=0.3.13 | OCR (Tesseract wrapper) |
| `spacy` | >=3.8.0 | NER (named entity recognition) |
| `llama-cpp-python` | >=0.3.0 | Local LLM inference |
| `cryptography` | >=44.0.0 | Fernet encryption, PBKDF2 |
| `python-multipart` | >=0.0.18 | File upload parsing |
| `pydantic` | >=2.10.0 | Data validation |
| `aiofiles` | >=24.1.0 | Async file serving |
| `transformers` | >=4.40.0 | BERT NER models |
| `torch` | >=2.2.0 | PyTorch (BERT/GLiNER backend) |
| `gliner` | >=0.2.0 | Zero-shot NER |
| `onnxruntime` | >=1.17.0 | ONNX model inference |
| `sentencepiece` | >=0.2.0 | Tokenization (BERT) |
| `PyMuPDF` | >=1.24.0 | PDF anonymization/detokenization |
| `psutil` | >=5.9.0 | System info (RAM check) |
| `httpx` | (transitive) | Remote LLM HTTP client |

### Optional Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `python-docx` | >=1.1.0 | DOCX processing |
| `openpyxl` | >=3.1.0 | XLSX processing |
| `python-pptx` | >=1.0.0 | PPTX processing |
| `reportlab` | (unlisted) | XLSX→PDF conversion |
| `lxml` | (transitive) | DOCX XML processing |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >=8.0.0 | Testing framework |
| `pytest-asyncio` | >=0.24.0 | Async test support |
| `httpx` | >=0.28.0 | API integration testing |
| `ruff` | >=0.8.0 | Linting & formatting |

### Observations
- **`reportlab`** is used in `_xlsx_to_pdf()` (loader.py) but **not declared** in pyproject.toml — this is a missing dependency
- **`lxml`** is used in `_replace_in_docx_xml_parts()` (engine.py) — transitive via python-docx but not explicitly listed
- Heavy dependency chain: `torch` + `transformers` + `spacy` adds ~2GB to the installed package size
- Version constraints use `>=` minimum — appropriate for an app (not a library)

---

## 6. Hardcoded Secrets & Security

### Secrets Assessment

| Finding | Status | Details |
|---------|--------|---------|
| API keys in source | **CLEAN** | LLM API key loaded from `DOC_ANON_LLM_API_KEY` env var |
| API key in settings response | **MASKED** | Shows `"...key_present..."` instead of real value |
| Vault passphrase | **CLEAN** | User-provided, never stored in plaintext |
| Firebase keys | **N/A** | Only in `src-licensing/`, not in backend |
| Hardcoded passwords | **CLEAN** | None found |
| Debug endpoints | **CLEAN** | No debug or admin backdoors |

### Security Model Assessment

| Area | Rating | Details |
|------|--------|---------|
| **Authentication** | N/A | No auth needed — local-only desktop sidecar |
| **CORS** | GOOD | Restricted to `localhost:1420`, `localhost:5173`, `tauri://localhost` |
| **Path traversal** | GOOD | Multiple protections: `_validate_doc_id()`, `_sanitize_filename()`, `resolve().relative_to()` |
| **File upload** | GOOD | 200MB limit, extension whitelist, MIME validation |
| **Vault encryption** | EXCELLENT | PBKDF2 (480k iterations) + Fernet, field-level encryption, passphrase verification |
| **Rate limiting** | GOOD | Sliding window + vault unlock brute-force protection |
| **Model loading** | GOOD | Path must be under `models_dir`, `.gguf` extension required |
| **Subprocess calls** | GOOD | LibreOffice and nvidia-smi with `capture_output=True`, no shell injection |
| **Temp file cleanup** | GOOD | Cleanup in lifespan shutdown handler |
| **SQL injection** | CLEAN | All SQLite queries use parameterized statements |

### Potential Security Improvements

1. **Vault database permissions**: No explicit `chmod 600` on the vault SQLite file
2. **Token manifest fallback**: If vault key is unavailable, manifest is saved in plaintext JSON (minus original text) — could leak token strings
3. **CORS wildcard risk**: If additional origins are added later, the list should be reviewed
4. **Remote LLM API key**: Stored in-memory as plaintext in `RemoteLLMEngine._api_key` — acceptable for desktop app but could be improved with secure memory handling

---

## 7. Test Coverage Assessment

### Coverage Map

| Module | Test File | Coverage Level | Gap |
|--------|-----------|:--------------:|-----|
| `core/detection/regex_detector.py` | `test_regex_detector.py` (655 lines) + `test_regex_bulletproof.py` (549 lines) | **HIGH** | Well-covered: validation, all PII types, false positives, international formats |
| `core/detection/region_shapes.py` | `test_region_shapes.py` (452 lines) | **HIGH** | Covers clamp, split, gap threshold, shape enforcement |
| `core/anonymizer/engine.py` | `test_anonymizer_engine.py` (423 lines) | **MEDIUM** | Context snippet, DOCX cross-run replacement, dispatch tested. PDF/XLSX/image handlers tested via mocks only |
| Italian language support | `test_italian.py` (344 lines) | **HIGH** | Italian addresses, postal codes, person labels, titles |
| `core/detection/block_offsets.py` + `ingestion/loader.py` | `test_offset_alignment.py` (299 lines) | **MEDIUM** | Line clustering, full_text build, offset computation, duplicate words |
| All API routers | `test_routers.py` (269 lines) | **LOW** | Health, settings, vault, LLM, detokenize, detection-progress. Missing: upload, actual detection, regions CRUD, anonymize, download |
| `core/vault/store.py` | `test_vault.py` (~100 lines) | **MEDIUM** | Store/resolve, list, delete, stats, register doc. Missing: export/import, wrong passphrase, close/reopen |
| `core/detokenize_file.py` | `test_detokenize_file.py` (~100 lines) | **LOW** | TXT/CSV paths only. PDF/DOCX/XLSX detokenization untested |
| `core/detection/ner_detector.py` | `test_ner_detector.py` (~50 lines) | **LOW** | Basic person/location/org detection only. Missing: chunking, false-positive filtering, language detection |

### Modules With NO Tests

| Module | Risk | Notes |
|--------|------|-------|
| `core/detection/merge.py` | **HIGH** | Cross-layer merge is the most complex detection logic |
| `core/detection/pipeline.py` | **HIGH** | Main orchestrator — only indirectly tested via NER/regex tests |
| `core/detection/bert_detector.py` | MEDIUM | BERT model loading, inference, label mapping |
| `core/detection/gliner_detector.py` | MEDIUM | GLiNER inference and filtering |
| `core/detection/llm_detector.py` | MEDIUM | LLM-based detection with JSON parsing |
| `core/detection/noise_filters.py` | LOW | Pure data module (noise term sets) |
| `core/detection/propagation.py` | MEDIUM | Cross-page region propagation |
| `core/detection/cross_line.py` | LOW | Cross-line ORG detection |
| `core/detection/language.py` | LOW | Language detection |
| `core/ingestion/loader.py` | **HIGH** | PDF extraction, OCR fallback, Office conversion |
| `core/llm/engine.py` | MEDIUM | LLM model loading and inference |
| `core/llm/remote_engine.py` | MEDIUM | Remote API calls with retry |
| `core/ocr/engine.py` | LOW | Tesseract integration |
| `core/persistence/store.py` | MEDIUM | Document persistence, atomic writes |
| `core/config.py` | LOW | Config loading/saving |
| `api/deps.py` | MEDIUM | Lock management, stale progress cleanup |
| `api/rate_limit.py` | LOW | Rate limiting logic |

### Test Quality Observations

- **Positive:** Tests use real fixtures and actual detection results (not excessive mocking)
- **Positive:** `test_regex_bulletproof.py` covers financial document false positives extensively
- **Positive:** Offset alignment tests verify deterministic behavior with noisy OCR data
- **Negative:** Integration tests (`test_routers.py`) are very shallow — mostly "does it return 200 OK?"
- **Negative:** No tests for the merge layer, which is where most detection bugs would surface
- **Negative:** No tests for PDF anonymization (actual PDF manipulation)
- **Negative:** No load/performance tests for large documents

### Recommended Test Additions (priority order)

1. **`test_merge.py`** — Cross-layer merge with overlapping detections, confidence boosting, ADDRESS fragment merging
2. **`test_pipeline_integration.py`** — Full detection pipeline on sample documents with known PII
3. **`test_ingestion.py`** — PDF text extraction accuracy, OCR fallback behavior
4. **`test_routers_integration.py`** — Upload → detect → review → anonymize → download round-trip
5. **`test_propagation.py`** — Cross-page region propagation correctness
6. **`test_vault_full.py`** — Export/import, wrong passphrase, concurrent access, close/reopen

---

## 8. Summary of Findings

### Strengths

1. **Clean architecture** — Well-separated layers: API → core modules → models
2. **Security-first vault design** — PBKDF2 + Fernet is solid for a desktop app
3. **Multi-layer detection** — Regex → NER → GLiNER → LLM with cross-layer confidence boosting
4. **Multi-format support** — PDF, DOCX, XLSX, images, with metadata scrubbing
5. **International coverage** — 6 languages, country-specific ID patterns, Italian/French deep support
6. **False-positive management** — 200+ noise terms, validation functions, context boosting
7. **Metadata handling** — Full scrub of PDF metadata, EXIF, XMP, annotations, attachments
8. **Proper async patterns** — `asyncio.to_thread()` for CPU-bound work
9. **Path traversal protection** — Multiple validation layers
10. **Type safety** — Pydantic v2 throughout, clean schema definitions

### Issues & Recommendations

| # | Severity | Finding | Recommendation |
|---|----------|---------|----------------|
| 1 | **MEDIUM** | Missing dependency: `reportlab` used in `loader.py` but not in `pyproject.toml` | Add `reportlab>=4.0` to dependencies |
| 2 | **MEDIUM** | No tests for `merge.py` (585 lines of complex logic) | Write unit tests for merge, confidence boosting, overlap resolution |
| 3 | **MEDIUM** | `ner_detector.py` at 981 lines — too large | Extract Italian detection, heuristic name detection, and false-positive filtering into separate modules |
| 4 | **LOW** | Detection logic duplicated between `detection.py` and `redetect` path | Extract shared detection orchestration into a helper function |
| 5 | **LOW** | `_stale_progress` dict in `deps.py` grows without bound during long sessions | Add periodic cleanup or TTL-based expiration |
| 6 | **LOW** | `_highlight_all_impl` in `regions.py` is O(n*m) fuzzy matching | Consider indexing or limiting fuzzy search to shorter needles |
| 7 | **LOW** | `_replace_in_docx_xml_parts` accesses `part._blob` internal API | Monitor python-docx version updates for breaking changes |
| 8 | **LOW** | `_xlsx_to_pdf` truncates cells at 100 chars and limits to 500 rows | Document the limitation or make it configurable |
| 9 | **INFO** | Italian language detection exists in both `ner_detector.py` and `language.py` | Consolidate into `language.py` |
| 10 | **INFO** | No vault file permissions set (e.g., `chmod 600`) | Add OS-level file permission restriction on vault creation |
| 11 | **INFO** | Router integration tests are very shallow | Expand to cover upload → detect → anonymize → download flow |

### Overall Assessment

**The codebase is well-structured and production-ready for a desktop application.** The security model is appropriate, the detection pipeline is sophisticated, and the code quality is generally high. The main gaps are in test coverage (particularly the merge layer and integration tests) and a few missing dependency declarations. No critical security vulnerabilities were found.
