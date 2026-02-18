"""Document upload, retrieval, listing, and deletion."""

from __future__ import annotations

import logging
import math
import time as _time
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from core.config import config
from models.schemas import (
    DocumentListItem,
    DocumentStatus,
    PaginatedDocumentList,
    RegionAction,
    UploadResponse,
)
from api.deps import documents, get_doc, get_store, prune_doc_locks, save_doc, upload_progress, cleanup_stale_upload_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/documents/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    progress_id: Optional[str] = Query(None, description="Optional ID for tracking upload progress")
) -> UploadResponse:
    """Upload a document for anonymization.
    
    If progress_id is provided, progress can be tracked via GET /documents/{progress_id}/upload-progress
    """
    from core.ingestion.loader import SUPPORTED_EXTENSIONS, guess_mime

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # S3: Reject filenames with path separators to prevent traversal
    if any(c in file.filename for c in ("/", "\\", "..")):
        raise HTTPException(400, "Invalid filename")

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
    
    # Use progress_id for tracking, or generate one
    tracking_id = progress_id or upload_id

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

    # Initialize progress tracking
    upload_progress[tracking_id] = {
        "doc_id": tracking_id,
        "status": "processing",
        "phase": "starting",
        "current_page": 0,
        "total_pages": 0,
        "ocr_pages_done": 0,
        "ocr_pages_total": 0,
        "message": "Starting document processing...",
        "elapsed_seconds": 0.0,
        "_started_at": _time.time(),
    }
    
    def _progress_callback(phase: str, current: int, total: int, ocr_done: int, ocr_total: int, message: str):
        """Update upload progress tracking."""
        if tracking_id in upload_progress:
            upload_progress[tracking_id].update({
                "phase": phase,
                "current_page": current,
                "total_pages": total,
                "ocr_pages_done": ocr_done,
                "ocr_pages_total": ocr_total,
                "message": message,
                "status": "complete" if phase == "complete" else "processing",
            })

    # Ingest the document
    from core.ingestion.loader import ingest_document

    try:
        doc = await ingest_document(upload_path, file.filename, progress_callback=_progress_callback)
        # Update tracking to include actual doc_id
        if tracking_id in upload_progress:
            upload_progress[tracking_id]["doc_id"] = doc.doc_id
            upload_progress[tracking_id]["status"] = "complete"
    except RuntimeError as e:
        # RuntimeError is raised for missing dependencies like LibreOffice
        logger.error(f"Failed to process document: {e}")
        if tracking_id in upload_progress:
            upload_progress[tracking_id]["status"] = "error"
            upload_progress[tracking_id]["error"] = str(e)
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Failed to process document: {e}")
        if tracking_id in upload_progress:
            upload_progress[tracking_id]["status"] = "error"
            upload_progress[tracking_id]["error"] = str(e)
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


@router.get("/documents/{doc_id}/upload-progress")
async def get_upload_progress(doc_id: str) -> dict[str, Any]:
    """Return real-time upload/ingestion progress for a document.
    
    Tracks file loading, page extraction, and OCR progress.
    """
    cleanup_stale_upload_progress()
    progress = upload_progress.get(doc_id)
    if progress is None:
        return {
            "doc_id": doc_id,
            "status": "idle",
            "phase": "idle",
            "current_page": 0,
            "total_pages": 0,
            "ocr_pages_done": 0,
            "ocr_pages_total": 0,
            "message": "",
            "elapsed_seconds": 0.0,
        }
    # Update elapsed time
    import time
    progress["elapsed_seconds"] = time.time() - progress.get("_started_at", time.time())
    # Return a clean copy (exclude internal keys)
    return {k: v for k, v in progress.items() if not k.startswith("_")}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str) -> dict[str, Any]:
    """Get document metadata and page info."""
    doc = get_doc(doc_id)
    return doc.model_dump(mode="json")


@router.get("/documents/{doc_id}/pages/{page_number}")
async def get_page(doc_id: str, page_number: int) -> dict[str, Any]:
    """Get page data including text blocks."""
    doc = get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number {page_number} (1-{doc.page_count})")
    page = doc.pages[page_number - 1]
    return page.model_dump(mode="json")


@router.get("/documents/{doc_id}/pages/{page_number}/bitmap")
async def get_page_bitmap(doc_id: str, page_number: int) -> FileResponse:
    """Serve the rendered page bitmap image."""
    doc = get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page number")
    page = doc.pages[page_number - 1]
    bitmap_path = Path(page.bitmap_path)
    if not bitmap_path.exists():
        raise HTTPException(404, "Bitmap not found")
    # S2: Ensure the resolved bitmap path is within the app's known directories
    # to prevent serving arbitrary files if persisted state were corrupted.
    # Bitmaps live in temp_dir (during ingestion) or data_dir (persisted).
    resolved = bitmap_path.resolve()
    allowed_dirs = (config.temp_dir.resolve(), config.data_dir.resolve())
    if not any(resolved.is_relative_to(d) for d in allowed_dirs):
        logger.warning("Blocked bitmap access outside app directories: %s", bitmap_path)
        raise HTTPException(403, "Access denied")
    return FileResponse(str(bitmap_path), media_type="image/png")


@router.get("/documents", response_model=Union[PaginatedDocumentList, list[DocumentListItem]])
async def list_documents(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    paginated: bool = Query(True, description="Return paginated response"),
) -> Union[PaginatedDocumentList, list[DocumentListItem]]:
    """List all uploaded documents with optional pagination.
    
    Args:
        page: Page number (1-indexed, default: 1)
        limit: Items per page (default: 50, max: 500)
        paginated: If True, return paginated response with metadata. If False, return flat list.
    """
    all_docs = sorted(documents.values(), key=lambda d: d.created_at, reverse=True)
    total = len(all_docs)
    
    # Build DocumentListItem for each document
    items = [
        DocumentListItem(
            doc_id=d.doc_id,
            original_filename=d.original_filename,
            filename=d.original_filename,
            file_path=d.file_path,
            mime_type=d.mime_type,
            page_count=d.page_count,
            status=d.status,
            regions_count=len(d.regions),
            is_protected=(
                len(d.regions) > 0
                and not any(r.action == RegionAction.PENDING for r in d.regions)
                and any(r.action in (RegionAction.TOKENIZE, RegionAction.REMOVE) for r in d.regions)
            ),
            created_at=d.created_at,
        )
        for d in all_docs
    ]
    
    if not paginated:
        return items
    
    # Apply pagination
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]
    pages = math.ceil(total / limit) if total > 0 else 1
    
    return PaginatedDocumentList(
        items=page_items,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str) -> dict[str, str]:
    """Delete a document and all its persisted data."""
    if doc_id not in documents:
        raise HTTPException(404, f"Document '{doc_id}' not found")

    del documents[doc_id]
    prune_doc_locks()

    try:
        store = get_store()
        store.delete_document(doc_id)
    except Exception as e:
        logger.error(f"Failed to delete persistent data for {doc_id}: {e}")

    return {"status": "ok", "doc_id": doc_id}
