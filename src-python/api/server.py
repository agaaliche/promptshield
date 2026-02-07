"""FastAPI application — main API for the document anonymizer sidecar."""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import config
from pydantic import BaseModel as _PydanticBaseModel
from models.schemas import (
    AnonymizeRequest,
    AnonymizeResponse,
    BatchActionRequest,
    BBox,
    DetectionProgress,
    DetokenizeRequest,
    DetokenizeResponse,
    DocumentInfo,
    DocumentStatus,
    LLMStatusResponse,
    PIIRegion,
    RegionAction,
    RegionActionRequest,
    RegionSyncItem,
    UploadResponse,
    VaultStatsResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Document Anonymizer",
    version="0.1.0",
    description="Offline document anonymizer with local LLM",
)

# CORS — allow Tauri webview and local dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri uses tauri://localhost or https://tauri.localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory state (in production, this could be a proper store)
# ---------------------------------------------------------------------------
_documents: dict[str, DocumentInfo] = {}


def _get_doc(doc_id: str) -> DocumentInfo:
    if doc_id not in _documents:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return _documents[doc_id]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    logger.info("Starting Document Anonymizer sidecar...")

    # Mount temp dir for serving page bitmaps
    config.temp_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/bitmaps",
        StaticFiles(directory=str(config.temp_dir)),
        name="bitmaps",
    )
    logger.info(f"Serving bitmaps from {config.temp_dir}")

    # Auto-load first available GGUF model if enabled
    if config.auto_load_llm:
        try:
            from core.llm.engine import llm_engine

            gguf_files = sorted(config.models_dir.glob("*.gguf"))
            if gguf_files:
                model_path = str(gguf_files[0])
                logger.info(f"Auto-loading LLM model: {gguf_files[0].name}")
                llm_engine.load_model(model_path)
                logger.info("LLM model loaded successfully")
            else:
                logger.info("No GGUF models found — skipping auto-load")
        except Exception as e:
            logger.warning(f"Auto-load LLM failed (non-fatal): {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Document upload & processing
# ---------------------------------------------------------------------------

@app.post("/api/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload a document for anonymization."""
    from core.ingestion.loader import SUPPORTED_EXTENSIONS, guess_mime

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Save uploaded file to temp
    upload_id = uuid.uuid4().hex[:8]
    upload_dir = config.temp_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / f"{upload_id}_{file.filename}"

    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info(f"Saved upload: {upload_path} ({len(content)} bytes)")

    # Ingest the document
    from core.ingestion.loader import ingest_document

    try:
        doc = await ingest_document(upload_path, file.filename)
    except Exception as e:
        raise HTTPException(500, f"Failed to process document: {e}")

    _documents[doc.doc_id] = doc

    return UploadResponse(
        doc_id=doc.doc_id,
        filename=doc.original_filename,
        page_count=doc.page_count,
        status=doc.status,
    )


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get document metadata and page info."""
    doc = _get_doc(doc_id)
    return doc.model_dump(mode="json")


@app.get("/api/documents/{doc_id}/pages/{page_number}")
async def get_page(doc_id: str, page_number: int):
    """Get page data including text blocks."""
    doc = _get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number {page_number} (1-{doc.page_count})")
    page = doc.pages[page_number - 1]
    return page.model_dump(mode="json")


@app.get("/api/documents/{doc_id}/pages/{page_number}/bitmap")
async def get_page_bitmap(doc_id: str, page_number: int):
    """Serve the rendered page bitmap image."""
    doc = _get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number")
    page = doc.pages[page_number - 1]
    bitmap_path = Path(page.bitmap_path)
    if not bitmap_path.exists():
        raise HTTPException(404, "Bitmap not found")
    return FileResponse(str(bitmap_path), media_type="image/png")


@app.get("/api/documents")
async def list_documents():
    """List all uploaded documents."""
    return [
        {
            "doc_id": d.doc_id,
            "original_filename": d.original_filename,
            "filename": d.original_filename,
            "page_count": d.page_count,
            "status": d.status.value,
            "regions_count": len(d.regions),
            "created_at": d.created_at.isoformat(),
        }
        for d in _documents.values()
    ]


# ---------------------------------------------------------------------------
# PII Detection
# ---------------------------------------------------------------------------

@app.post("/api/documents/{doc_id}/detect")
async def detect_pii(doc_id: str):
    """
    Run PII detection on all pages of a document.

    Returns the list of detected PII regions.
    """
    from core.detection.pipeline import detect_pii_on_page
    from core.llm.engine import llm_engine

    doc = _get_doc(doc_id)
    doc.status = DocumentStatus.DETECTING
    doc.regions = []

    engine = llm_engine if llm_engine.is_loaded() else None

    for page in doc.pages:
        regions = detect_pii_on_page(page, llm_engine=engine)
        doc.regions.extend(regions)

    doc.status = DocumentStatus.REVIEWING
    logger.info(f"Detection complete for '{doc.original_filename}': {len(doc.regions)} regions")

    return {
        "doc_id": doc_id,
        "total_regions": len(doc.regions),
        "regions": [r.model_dump(mode="json") for r in doc.regions],
    }


@app.get("/api/documents/{doc_id}/regions")
async def get_regions(doc_id: str, page_number: Optional[int] = None):
    """Get detected PII regions, optionally filtered by page."""
    doc = _get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    return [r.model_dump(mode="json") for r in regions]


@app.put("/api/documents/{doc_id}/regions/{region_id}/action")
async def set_region_action(doc_id: str, region_id: str, req: RegionActionRequest):
    """Set the action for a specific PII region."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.action = req.action
            return {"status": "ok", "region_id": region_id, "action": req.action.value}
    raise HTTPException(404, f"Region '{region_id}' not found")


@app.put("/api/documents/{doc_id}/regions/{region_id}/bbox")
async def update_region_bbox(doc_id: str, region_id: str, bbox: BBox):
    """Update the bounding box of a PII region (move / resize)."""
    doc = _get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.bbox = bbox
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


@app.put("/api/documents/{doc_id}/regions/batch-action")
async def batch_region_action(doc_id: str, req: BatchActionRequest):
    """Apply an action to multiple regions at once."""
    doc = _get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    updated = 0
    for rid in req.region_ids:
        if rid in region_map:
            region_map[rid].action = req.action
            updated += 1
    return {"status": "ok", "updated": updated}


@app.post("/api/documents/{doc_id}/regions/add")
async def add_manual_region(doc_id: str, region: PIIRegion):
    """Add a manually selected PII region."""
    doc = _get_doc(doc_id)
    region.source = "MANUAL"
    doc.regions.append(region)
    return {"status": "ok", "region_id": region.id}


# ---------------------------------------------------------------------------
# Sync & Anonymization
# ---------------------------------------------------------------------------

@app.put("/api/documents/{doc_id}/regions/sync")
async def sync_regions(doc_id: str, items: list[RegionSyncItem]):
    """Bulk-sync region actions and bboxes from the frontend.

    Called right before anonymize to guarantee the backend has the latest
    user edits (moved/resized regions, changed actions) regardless of
    whether individual PUT calls have completed."""
    doc = _get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    synced = 0
    for item in items:
        r = region_map.get(item.id)
        if r:
            r.action = item.action
            r.bbox = item.bbox
            synced += 1
    return {"status": "ok", "synced": synced}


@app.post("/api/documents/{doc_id}/anonymize", response_model=AnonymizeResponse)
async def anonymize(doc_id: str):
    """Apply anonymization to the document based on region actions."""
    from core.anonymizer.engine import anonymize_document

    doc = _get_doc(doc_id)
    doc.status = DocumentStatus.ANONYMIZING

    try:
        result = await anonymize_document(doc)
        doc.status = DocumentStatus.COMPLETED
        return result
    except Exception as e:
        doc.status = DocumentStatus.ERROR
        raise HTTPException(500, f"Anonymization failed: {e}")


@app.get("/api/documents/{doc_id}/download/{file_type}")
async def download_output(doc_id: str, file_type: str):
    """Download the anonymized output file (pdf or text)."""
    doc = _get_doc(doc_id)
    output_dir = config.temp_dir / doc_id / "output"

    if file_type == "pdf":
        files = list(output_dir.glob("*_anonymized_*.pdf"))
    elif file_type == "text":
        files = list(output_dir.glob("*_anonymized_*.txt"))
    else:
        raise HTTPException(400, "file_type must be 'pdf' or 'text'")

    if not files:
        raise HTTPException(404, "Output file not found. Run anonymization first.")

    # Return the latest file
    latest = max(files, key=lambda f: f.stat().st_mtime)
    media_type = "application/pdf" if file_type == "pdf" else "text/plain"
    return FileResponse(str(latest), media_type=media_type, filename=latest.name)


# ---------------------------------------------------------------------------
# De-tokenization
# ---------------------------------------------------------------------------

@app.post("/api/detokenize", response_model=DetokenizeResponse)
async def detokenize(req: DetokenizeRequest):
    """Replace tokens in text with their original values."""
    from core.vault.store import vault

    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked. Unlock it first.")

    result_text, count, unresolved = vault.resolve_all_tokens(req.text)
    return DetokenizeResponse(
        original_text=result_text,
        tokens_replaced=count,
        unresolved_tokens=unresolved,
    )


@app.post("/api/detokenize/file")
async def detokenize_file_endpoint(file: UploadFile = File(...)):
    """De-tokenize tokens inside an uploaded file (.docx, .xlsx, .pdf, .txt, .csv).

    Returns the processed file as a download.
    Metadata (tokens_replaced, unresolved) is passed via response headers.
    """
    from core.vault.store import vault
    from core.detokenize_file import detokenize_file, SUPPORTED_EXTENSIONS

    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked. Unlock it first.")

    filename = file.filename or "unknown.txt"
    data = await file.read()

    try:
        out_bytes, out_name, count, unresolved = detokenize_file(data, filename, vault)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"File de-tokenization failed: {e}")
        raise HTTPException(500, f"De-tokenization failed: {e}")

    # Determine media type
    ext = Path(out_name).suffix.lower()
    media_types = {
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    # Write to temp file and return
    import tempfile, os
    tmp = Path(tempfile.mkdtemp(dir=str(config.temp_dir)))
    out_path = tmp / out_name
    out_path.write_bytes(out_bytes)

    headers = {
        "X-Tokens-Replaced": str(count),
        "X-Unresolved-Tokens": ",".join(unresolved) if unresolved else "",
        "Access-Control-Expose-Headers": "X-Tokens-Replaced, X-Unresolved-Tokens",
    }

    return FileResponse(
        str(out_path),
        media_type=media_type,
        filename=out_name,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Vault management
# ---------------------------------------------------------------------------

class _PassphraseBody(_PydanticBaseModel):
    passphrase: str


@app.post("/api/vault/unlock")
async def unlock_vault(body: _PassphraseBody):
    """Unlock the token vault with a passphrase."""
    from core.vault.store import vault

    try:
        vault.initialize(body.passphrase)
        return {"status": "ok", "message": "Vault unlocked"}
    except ValueError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to open vault: {e}")


@app.get("/api/vault/status")
async def vault_status():
    """Check vault status."""
    from core.vault.store import vault
    return {
        "unlocked": vault.is_unlocked,
        "path": str(vault.db_path),
    }


@app.get("/api/vault/stats", response_model=VaultStatsResponse)
async def vault_stats():
    """Get vault statistics."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    stats = vault.get_stats()
    return VaultStatsResponse(**stats)


@app.get("/api/vault/tokens")
async def list_vault_tokens(source_document: Optional[str] = None):
    """List all tokens in the vault."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    tokens = vault.list_tokens(source_document=source_document)
    return [t.model_dump(mode="json") for t in tokens]


# ---------------------------------------------------------------------------
# LLM management
# ---------------------------------------------------------------------------

@app.get("/api/llm/status", response_model=LLMStatusResponse)
async def llm_status():
    """Get LLM engine status."""
    from core.llm.engine import llm_engine
    return LLMStatusResponse(
        loaded=llm_engine.is_loaded(),
        model_name=llm_engine.model_name,
        model_path=llm_engine.model_path,
        gpu_enabled=llm_engine.gpu_enabled,
        context_size=config.llm_context_size,
    )


@app.post("/api/llm/load")
async def load_llm(model_path: str, force_cpu: bool = False):
    """Load a GGUF model."""
    from core.llm.engine import llm_engine
    try:
        llm_engine.load_model(model_path, force_cpu=force_cpu)
        return {"status": "ok", "model": llm_engine.model_name}
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")


@app.post("/api/llm/unload")
async def unload_llm():
    """Unload the current LLM model."""
    from core.llm.engine import llm_engine
    llm_engine.unload_model()
    return {"status": "ok"}


@app.get("/api/llm/models")
async def list_models():
    """List available GGUF models in the models directory."""
    from core.llm.engine import llm_engine
    return llm_engine.list_available_models()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings():
    """Get current app settings."""
    return config.model_dump(mode="json")


@app.patch("/api/settings")
async def update_settings(updates: dict):
    """Update app settings (partial update)."""
    allowed = {
        "regex_enabled", "ner_enabled", "llm_detection_enabled",
        "confidence_threshold", "ocr_language", "ocr_dpi",
        "render_dpi", "tesseract_cmd",
        "ner_backend", "ner_model_preference",
    }
    applied = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if hasattr(config, key):
            setattr(config, key, value)
            applied[key] = value

    # When the NER backend changes, unload the cached BERT pipeline so the
    # newly selected model is loaded on the next detection run.
    if "ner_backend" in applied:
        try:
            from core.detection.bert_detector import unload_pipeline
            unload_pipeline()
            logger.info(f"NER backend changed to '{applied['ner_backend']}' — BERT pipeline unloaded")
        except Exception:
            pass  # non-fatal; pipeline will reload on next detection

    # Persist to disk so settings survive server restarts
    if applied:
        config.save_user_settings()

    return {"status": "ok", "applied": applied}


# ---------------------------------------------------------------------------
# Vault export
# ---------------------------------------------------------------------------

@app.post("/api/vault/export")
async def export_vault(passphrase: str):
    """Export all vault tokens as encrypted JSON."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    try:
        data = vault.export_vault(passphrase)
        return JSONResponse(content={"export": data})
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")
