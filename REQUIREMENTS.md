# Requirements

## System Prerequisites

| Requirement | Version | Required | Notes |
|---|---|---|---|
| **Node.js** | ≥ 18 | Yes | Frontend build & dev server |
| **npm** | ≥ 9 | Yes | Included with Node.js |
| **Python** | ≥ 3.11 | Yes | Backend runtime |
| **pip** | latest | Yes | Included with Python |
| **Git** | any | Recommended | Version control |
| **Rust** | ≥ 1.70 | Optional | Tauri desktop builds only |
| **MSVC Build Tools** | 2019+ | Optional | Required on Windows for `llama-cpp-python` and Tauri |
| **Tesseract OCR** | ≥ 5.0 | Optional | Scanned / image-based PDFs |

### Install links

- Node.js — <https://nodejs.org>
- Python — <https://www.python.org/downloads/>
- Rust — <https://rustup.rs>
- MSVC Build Tools — <https://visualstudio.microsoft.com/visual-cpp-build-tools/>
- Tesseract (Windows) — <https://github.com/UB-Mannheim/tesseract/wiki>

---

## Python Dependencies

> Defined in `src-python/pyproject.toml`. Install with:
> ```
> pip install -e .[dev,office]
> ```

### Core

| Package | Min Version | Purpose |
|---|---|---|
| fastapi | 0.115.0 | REST API framework |
| uvicorn[standard] | 0.34.0 | ASGI server |
| pydantic | 2.10.0 | Data validation / schemas |
| python-multipart | 0.0.18 | File upload handling |
| aiofiles | 24.1.0 | Async file I/O |

### Document Processing

| Package | Min Version | Purpose |
|---|---|---|
| pypdfium2 | 4.30.0 | PDF rendering to images |
| PyMuPDF | 1.24.0 | PDF text extraction & redaction |
| Pillow | 11.0.0 | Image processing |
| pytesseract | 0.3.13 | OCR (requires Tesseract binary) |

### NLP / Detection

| Package | Min Version | Purpose |
|---|---|---|
| spacy | 3.8.0 | Named Entity Recognition |
| transformers | 4.40.0 | BERT-based NER models |
| torch | 2.2.0 | PyTorch (transformer backend) |
| gliner | 0.2.0 | GLiNER entity detection |
| onnxruntime | 1.17.0 | ONNX model inference |
| sentencepiece | 0.2.0 | Tokenizer for transformer models |
| llama-cpp-python | 0.3.0 | Local LLM inference (GGUF) |

### Security

| Package | Min Version | Purpose |
|---|---|---|
| cryptography | 44.0.0 | AES-GCM encryption for token vault |

### spaCy Models

Download after installing packages:

```bash
python -m spacy download en_core_web_sm    # lightweight (default)
python -m spacy download en_core_web_lg    # better accuracy
```

### Optional: Dev Tools

| Package | Min Version | Purpose |
|---|---|---|
| pytest | 8.0.0 | Test runner |
| pytest-asyncio | 0.24.0 | Async test support |
| httpx | 0.28.0 | Async HTTP client for tests |
| ruff | 0.8.0 | Linter & formatter |

### Optional: Office File Support

| Package | Min Version | Purpose |
|---|---|---|
| python-docx | 1.1.0 | Word documents (.docx) |
| openpyxl | 3.1.0 | Excel spreadsheets (.xlsx) |
| python-pptx | 1.0.0 | PowerPoint presentations (.pptx) |

---

## Frontend Dependencies

> Defined in `frontend/package.json`. Install with:
> ```
> cd frontend && npm install
> ```

### Runtime

| Package | Version | Purpose |
|---|---|---|
| react | ^19.2.0 | UI framework |
| react-dom | ^19.2.0 | DOM rendering |
| react-router-dom | ^7.13.0 | Client-side routing |
| zustand | ^5.0.11 | State management |
| lucide-react | ^0.563.0 | Icon library |
| @tauri-apps/api | ^2.10.1 | Tauri desktop APIs |
| @tauri-apps/cli | ^2.10.0 | Tauri CLI |

### Dev

| Package | Version | Purpose |
|---|---|---|
| typescript | ~5.9.3 | Type system |
| vite | ^7.2.4 | Dev server & bundler |
| vitest | ^4.0.18 | Test runner |
| eslint | ^9.39.1 | Linter |
| @vitejs/plugin-react | ^5.1.1 | React HMR plugin |
| @testing-library/react | ^16.3.2 | Component testing |
| jsdom | ^28.0.0 | DOM simulation for tests |

---

## Tauri / Rust Dependencies (Desktop only)

> Defined in `frontend/src-tauri/Cargo.toml`. Managed automatically by `cargo`.

| Crate | Purpose |
|---|---|
| tauri | Desktop app framework |
| tauri-build | Build script |
| serde / serde_json | Serialization |

---

## Optional Downloads

| Item | Purpose | Notes |
|---|---|---|
| **GGUF model file** | LLM-based PII detection | Any GGUF-compatible model; set path in app Settings |
| **Tesseract language data** | OCR for non-English docs | Place `.traineddata` files in Tesseract `tessdata/` directory |

---

## Quick Setup

```powershell
# Automated (Windows)
.\setup.ps1

# Manual
cd src-python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev,office]
python -m spacy download en_core_web_sm

cd ..\frontend
npm install
```

## Ports

| Service | Port |
|---|---|
| Backend API | 8910 |
| Frontend dev server | 5173 |
