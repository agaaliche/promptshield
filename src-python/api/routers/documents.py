"""Document upload, retrieval, listing, and deletion."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from core.config import config
from models.schemas import (
    RegionAction,
    UploadResponse,
)
from api.deps import documents, get_doc, get_store, save_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload", response_model=UploadResponse)
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
    safe_name = Path(file.filename).name  # strip directory components (path-traversal)
    upload_path = upload_dir / f"{upload_id}_{safe_name}"

    MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
    with open(upload_path, "wb") as f:
        total = 0
        while chunk := await file.read(256 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                f.close()
                upload_path.unlink(missing_ok=True)
                raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")
            f.write(chunk)

    logger.info(f"Saved upload: {upload_path} ({total} bytes)")

    # Ingest the document
    from core.ingestion.loader import ingest_document

    try:
        doc = await ingest_document(upload_path, file.filename)
    except RuntimeError as e:
        # RuntimeError is raised for missing dependencies like LibreOffice
        logger.error(f"Failed to process document: {e}")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to process document: {e}")
        raise HTTPException(500, f"Failed to process document: {e}")

    # Store file in persistent storage
    store = get_store()
    try:
        stored_file_path = store.store_uploaded_file(doc.doc_id, upload_path, file.filename)
        doc.file_path = str(stored_file_path)
        logger.info(f"Stored file permanently: {stored_file_path}")
    except Exception as e:
        logger.error(f"Failed to store file permanently: {e}")
    finally:
        # Clean up temporary upload file
        upload_path.unlink(missing_ok=True)

    # Copy page bitmaps to persistent storage
    try:
        store.store_page_bitmaps(doc)
        logger.info(f"Stored {len(doc.pages)} page bitmaps for {doc.doc_id}")
    except Exception as e:
        logger.error(f"Failed to store bitmaps: {e}")

    # Save document state
    documents[doc.doc_id] = doc
    try:
        store.save_document(doc)
        logger.info(f"Saved document state for {doc.doc_id}")
    except Exception as e:
        logger.error(f"Failed to save document state: {e}")

    return UploadResponse(
        doc_id=doc.doc_id,
        filename=doc.original_filename,
        page_count=doc.page_count,
        status=doc.status,
    )


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get document metadata and page info."""
    doc = get_doc(doc_id)
    return doc.model_dump(mode="json")


@router.get("/documents/{doc_id}/pages/{page_number}")
async def get_page(doc_id: str, page_number: int):
    """Get page data including text blocks."""
    doc = get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number {page_number} (1-{doc.page_count})")
    page = doc.pages[page_number - 1]
    return page.model_dump(mode="json")


@router.get("/documents/{doc_id}/pages/{page_number}/bitmap")
async def get_page_bitmap(doc_id: str, page_number: int):
    """Serve the rendered page bitmap image."""
    doc = get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number")
    page = doc.pages[page_number - 1]
    bitmap_path = Path(page.bitmap_path)
    if not bitmap_path.exists():
        raise HTTPException(404, "Bitmap not found")
    return FileResponse(str(bitmap_path), media_type="image/png")


@router.get("/documents")
async def list_documents():
    """List all uploaded documents."""
    return [
        {
            "doc_id": d.doc_id,
            "original_filename": d.original_filename,
            "filename": d.original_filename,
            "file_path": d.file_path,
            "mime_type": d.mime_type,
            "page_count": d.page_count,
            "status": d.status.value,
            "regions_count": len(d.regions),
            "is_protected": (
                len(d.regions) > 0
                and not any(r.action == RegionAction.PENDING for r in d.regions)
                and any(r.action in (RegionAction.TOKENIZE, RegionAction.REMOVE) for r in d.regions)
            ),
            "created_at": d.created_at.isoformat(),
        }
        for d in documents.values()
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and all its persisted data."""
    if doc_id not in documents:
        raise HTTPException(404, f"Document '{doc_id}' not found")

    del documents[doc_id]

    try:
        store = get_store()
        store.delete_document(doc_id)
    except Exception as e:
        logger.error(f"Failed to delete persistent data for {doc_id}: {e}")

    return {"status": "ok", "doc_id": doc_id}
