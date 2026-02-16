"""Region sync, anonymization, file download, and batch export."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel as _PydanticBaseModel
from starlette.background import BackgroundTask

from core.config import config
from models.schemas import (
    AnonymizeResponse,
    DocumentStatus,
    RegionSyncItem,
)
from api.deps import documents, get_doc, save_doc, _clamp_bbox, export_progress, cleanup_stale_export_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["anonymize"])


@router.put("/documents/{doc_id}/regions/sync")
async def sync_regions(doc_id: str, items: list[RegionSyncItem]) -> dict[str, Any]:
    """Bulk-sync region actions and bboxes from the frontend.

    Called right before anonymize to guarantee the backend has the latest
    user edits (moved/resized regions, changed actions) regardless of
    whether individual PUT calls have completed."""
    doc = get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    page_map = {p.page_number: p for p in doc.pages}
    synced = 0
    for item in items:
        r = region_map.get(item.id)
        if r:
            r.action = item.action
            # Clamp synced bbox to page bounds
            pd = page_map.get(r.page_number)
            r.bbox = _clamp_bbox(item.bbox, pd.width, pd.height) if pd else item.bbox
            synced += 1
    save_doc(doc)
    return {"status": "ok", "synced": synced}


@router.post("/documents/{doc_id}/anonymize", response_model=AnonymizeResponse)
async def anonymize(doc_id: str) -> AnonymizeResponse:
    """Apply anonymization to the document based on region actions."""
    doc = get_doc(doc_id)  # 404 before heavy imports
    from core.anonymizer.engine import anonymize_document
    doc.status = DocumentStatus.ANONYMIZING

    try:
        result = await anonymize_document(doc)
        doc.status = DocumentStatus.COMPLETED
        save_doc(doc)
        return result
    except Exception as e:
        import traceback
        logger.error(f"Anonymization failed:\n{traceback.format_exc()}")
        doc.status = DocumentStatus.ERROR
        save_doc(doc)
        raise HTTPException(500, "Anonymization failed. Check server logs for details.")


@router.get("/documents/{doc_id}/download/{file_type}")
async def download_output(doc_id: str, file_type: str) -> FileResponse:
    """Download the anonymized output file (pdf or text)."""
    doc = get_doc(doc_id)
    output_dir = config.temp_dir / doc_id / "output"

    if file_type == "pdf":
        files = list(output_dir.glob("*_anonymized_*.pdf"))
    elif file_type == "text":
        files = list(output_dir.glob("*_anonymized_*.txt"))
    else:
        raise HTTPException(400, "file_type must be 'pdf' or 'text'")

    if not files:
        raise HTTPException(404, "Output file not found. Run anonymization first.")

    latest = max(files, key=lambda f: f.stat().st_mtime)
    # S2: Ensure resolved file is within expected output directory
    if not latest.resolve().is_relative_to(output_dir.resolve()):
        raise HTTPException(403, "Access denied")
    media_type = "application/pdf" if file_type == "pdf" else "text/plain"
    return FileResponse(str(latest), media_type=media_type, filename=latest.name)


class BatchAnonymizeRequest(_PydanticBaseModel):
    doc_ids: list[str]


class BatchAnonymizeResult(_PydanticBaseModel):
    doc_id: str
    success: bool
    error: Optional[str] = None
    tokens_created: int = 0
    regions_removed: int = 0


@router.post("/documents/batch-anonymize")
async def batch_anonymize(req: BatchAnonymizeRequest) -> FileResponse:
    """Anonymize multiple documents. If >1 doc, returns a zip archive."""
    if not req.doc_ids:
        raise HTTPException(400, "No documents selected")
    if len(req.doc_ids) > 50:
        raise HTTPException(400, "Maximum 50 documents per export")

    import asyncio
    import zipfile
    import tempfile
    import time
    from core.anonymizer.engine import anonymize_document

    logger.info(f"Batch export starting for {len(req.doc_ids)} documents: {req.doc_ids}")
    start_time = time.time()

    output_files: list[tuple[str, Path]] = []
    files_lock = asyncio.Lock()
    
    # Limit concurrency to avoid overwhelming the system
    semaphore = asyncio.Semaphore(3)
    
    async def process_one(doc_id: str) -> BatchAnonymizeResult:
        async with semaphore:
            doc_start = time.time()
            try:
                logger.info(f"[{doc_id}] Starting anonymization...")
                doc = get_doc(doc_id)
                doc.status = DocumentStatus.ANONYMIZING
                result = await anonymize_document(doc)
                doc.status = DocumentStatus.COMPLETED
                save_doc(doc)
                
                output_dir = config.temp_dir / doc_id / "output"
                pdfs = list(output_dir.glob("*_anonymized_*.pdf"))
                if pdfs:
                    latest = max(pdfs, key=lambda f: f.stat().st_mtime)
                    async with files_lock:
                        output_files.append((latest.name, latest))
                
                elapsed = time.time() - doc_start
                logger.info(f"[{doc_id}] Completed in {elapsed:.2f}s")
                return BatchAnonymizeResult(
                    doc_id=doc_id, success=True,
                    tokens_created=result.tokens_created,
                    regions_removed=result.regions_removed,
                )
            except Exception as e:
                elapsed = time.time() - doc_start
                logger.error(f"[{doc_id}] Failed after {elapsed:.2f}s: {e}")
                return BatchAnonymizeResult(
                    doc_id=doc_id, success=False, error=str(e),
                )
    
    # Process all documents concurrently (limited by semaphore)
    results = await asyncio.gather(*[process_one(doc_id) for doc_id in req.doc_ids])
    
    total_elapsed = time.time() - start_time
    logger.info(f"Batch export completed in {total_elapsed:.2f}s")

    successful = [r for r in results if r.success]

    if len(req.doc_ids) == 1 and len(output_files) == 1:
        _, path = output_files[0]
        return FileResponse(str(path), media_type="application/pdf", filename=path.name)

    if not output_files:
        raise HTTPException(500, "No files were successfully anonymized")

    zip_fd, zip_str = tempfile.mkstemp(suffix=".zip", prefix="promptshield_export_")
    zip_path = Path(zip_str)
    os.close(zip_fd)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, fpath in output_files:
            zf.write(fpath, fname)

    async def _cleanup() -> None:
        zip_path.unlink(missing_ok=True)

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename="promptshield_export.zip",
        background=BackgroundTask(_cleanup),
    )


class ExportSaveResponse(_PydanticBaseModel):
    saved_path: str
    filename: str
    file_count: int
    total_size: int


class ExportToDownloadsRequest(_PydanticBaseModel):
    doc_ids: list[str]
    export_id: Optional[str] = None


@router.get("/documents/export-progress/{export_id}")
async def get_export_progress(export_id: str) -> dict[str, Any]:
    """Return real-time export/anonymization progress."""
    cleanup_stale_export_progress()
    progress = export_progress.get(export_id)
    if progress is None:
        return {
            "export_id": export_id,
            "status": "idle",
            "phase": "idle",
            "docs_done": 0,
            "docs_total": 0,
            "current_doc_name": "",
            "message": "",
            "elapsed_seconds": 0.0,
        }
    import time
    result = {k: v for k, v in progress.items() if not k.startswith("_")}
    result["elapsed_seconds"] = time.time() - progress.get("_started_at", time.time())
    return result


@router.post("/documents/export-to-downloads")
async def export_to_downloads(req: ExportToDownloadsRequest) -> ExportSaveResponse:
    """Anonymize documents and save the result to the user's Downloads folder.

    Returns the full path so the frontend can offer Open File / Open Folder buttons.
    """
    import asyncio
    import shutil
    import zipfile
    import tempfile
    import time
    from core.anonymizer.engine import anonymize_document

    if not req.doc_ids:
        raise HTTPException(400, "No documents selected")
    if len(req.doc_ids) > 50:
        raise HTTPException(400, "Maximum 50 documents per export")

    tracking_id = req.export_id or f"export-{int(time.time() * 1000)}"

    logger.info(f"Export-to-downloads starting for {len(req.doc_ids)} documents")
    start_time = time.time()

    # Initialize progress tracking
    doc_names = {}
    for doc_id in req.doc_ids:
        try:
            doc_names[doc_id] = get_doc(doc_id).original_filename
        except Exception:
            doc_names[doc_id] = doc_id

    export_progress[tracking_id] = {
        "export_id": tracking_id,
        "status": "processing",
        "phase": "anonymizing",
        "docs_done": 0,
        "docs_total": len(req.doc_ids),
        "docs_failed": 0,
        "current_doc_name": "",
        "message": f"Anonymizing {len(req.doc_ids)} document(s)…",
        "doc_statuses": [
            {"doc_id": d, "name": doc_names[d], "status": "pending"} for d in req.doc_ids
        ],
        "elapsed_seconds": 0.0,
        "_started_at": start_time,
    }

    output_files: list[tuple[str, Path]] = []
    files_lock = asyncio.Lock()
    docs_done = 0
    docs_failed = 0
    semaphore = asyncio.Semaphore(3)

    async def process_one(doc_id: str) -> None:
        nonlocal docs_done, docs_failed
        async with semaphore:
            try:
                # Update progress — mark as running
                if tracking_id in export_progress:
                    for ds in export_progress[tracking_id].get("doc_statuses", []):
                        if ds["doc_id"] == doc_id:
                            ds["status"] = "running"
                    export_progress[tracking_id]["current_doc_name"] = doc_names.get(doc_id, doc_id)
                    export_progress[tracking_id]["message"] = f"Anonymizing {doc_names.get(doc_id, doc_id)}…"

                doc = get_doc(doc_id)
                doc.status = DocumentStatus.ANONYMIZING
                await anonymize_document(doc)
                doc.status = DocumentStatus.COMPLETED
                save_doc(doc)

                output_dir = config.temp_dir / doc_id / "output"
                pdfs = list(output_dir.glob("*_anonymized_*.pdf"))
                if pdfs:
                    latest = max(pdfs, key=lambda f: f.stat().st_mtime)
                    async with files_lock:
                        output_files.append((latest.name, latest))

                # Update progress — mark as done
                docs_done += 1
                if tracking_id in export_progress:
                    for ds in export_progress[tracking_id].get("doc_statuses", []):
                        if ds["doc_id"] == doc_id:
                            ds["status"] = "done"
                    export_progress[tracking_id]["docs_done"] = docs_done
                    export_progress[tracking_id]["message"] = f"Anonymized {docs_done}/{len(req.doc_ids)} document(s)"
            except Exception as e:
                logger.error(f"[{doc_id}] Export failed: {e}")
                docs_failed += 1
                if tracking_id in export_progress:
                    for ds in export_progress[tracking_id].get("doc_statuses", []):
                        if ds["doc_id"] == doc_id:
                            ds["status"] = "error"
                            ds["error"] = str(e)
                    export_progress[tracking_id]["docs_done"] = docs_done
                    export_progress[tracking_id]["docs_failed"] = docs_failed

    await asyncio.gather(*[process_one(doc_id) for doc_id in req.doc_ids])

    if not output_files:
        if tracking_id in export_progress:
            export_progress[tracking_id]["status"] = "error"
            export_progress[tracking_id]["message"] = "No files were successfully anonymized"
        raise HTTPException(500, "No files were successfully anonymized")

    # Update progress — saving phase
    if tracking_id in export_progress:
        export_progress[tracking_id]["phase"] = "saving"
        export_progress[tracking_id]["message"] = "Saving to Downloads folder…"

    # Determine Downloads folder
    downloads_dir = _get_downloads_folder()
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if len(output_files) == 1:
        # Single file → copy PDF directly
        _, src_path = output_files[0]
        dest_name = src_path.name
        dest = downloads_dir / dest_name
        # Avoid overwriting — append (1), (2), etc.
        counter = 1
        while dest.exists():
            stem = src_path.stem
            dest = downloads_dir / f"{stem} ({counter}).pdf"
            counter += 1
        shutil.copy2(str(src_path), str(dest))
        total_size = dest.stat().st_size
    else:
        # Multiple files → zip
        dest = downloads_dir / "promptshield_export.zip"
        counter = 1
        while dest.exists():
            dest = downloads_dir / f"promptshield_export ({counter}).zip"
            counter += 1
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname, fpath in output_files:
                zf.write(fpath, fname)
        total_size = dest.stat().st_size

    elapsed = time.time() - start_time
    logger.info(f"Export saved to {dest} in {elapsed:.2f}s ({total_size} bytes)")

    # Mark export progress as complete
    if tracking_id in export_progress:
        export_progress[tracking_id]["status"] = "complete"
        export_progress[tracking_id]["phase"] = "complete"
        export_progress[tracking_id]["message"] = f"Saved to {dest.name}"

    return ExportSaveResponse(
        saved_path=str(dest),
        filename=dest.name,
        file_count=len(output_files),
        total_size=total_size,
    )


def _get_downloads_folder() -> Path:
    """Return the user's Downloads folder (cross-platform)."""
    import platform as _platform
    system = _platform.system()
    if system == "Windows":
        # Use the known folder path; fallback to USERPROFILE/Downloads
        import ctypes
        from ctypes import wintypes
        FOLDERID_Downloads = "{374DE290-123F-4565-9164-39C4925E467B}"
        try:
            buf = ctypes.c_wchar_p()
            ctypes.windll.shell32.SHGetKnownFolderPath(  # type: ignore[attr-defined]
                ctypes.create_string_buffer(FOLDERID_Downloads.encode()),
                0, None, ctypes.byref(buf),
            )
            if buf.value:
                return Path(buf.value)
        except Exception:
            pass
    # Fallback: ~/Downloads
    return Path.home() / "Downloads"
