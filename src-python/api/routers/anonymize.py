"""Region sync, anonymization, file download, and batch export."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

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
from api.deps import documents, get_doc, save_doc, _clamp_bbox

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["anonymize"])


@router.put("/documents/{doc_id}/regions/sync")
async def sync_regions(doc_id: str, items: list[RegionSyncItem]):
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
async def anonymize(doc_id: str):
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
async def download_output(doc_id: str, file_type: str):
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
async def batch_anonymize(req: BatchAnonymizeRequest):
    """Anonymize multiple documents. If >1 doc, returns a zip archive."""
    if not req.doc_ids:
        raise HTTPException(400, "No documents selected")
    if len(req.doc_ids) > 50:
        raise HTTPException(400, "Maximum 50 documents per export")

    import zipfile
    import tempfile
    from core.anonymizer.engine import anonymize_document

    results: list[BatchAnonymizeResult] = []
    output_files: list[tuple[str, Path]] = []

    for doc_id in req.doc_ids:
        try:
            doc = get_doc(doc_id)
            doc.status = DocumentStatus.ANONYMIZING
            result = await anonymize_document(doc)
            doc.status = DocumentStatus.COMPLETED
            save_doc(doc)
            results.append(BatchAnonymizeResult(
                doc_id=doc_id, success=True,
                tokens_created=result.tokens_created,
                regions_removed=result.regions_removed,
            ))
            output_dir = config.temp_dir / doc_id / "output"
            pdfs = list(output_dir.glob("*_anonymized_*.pdf"))
            if pdfs:
                latest = max(pdfs, key=lambda f: f.stat().st_mtime)
                output_files.append((latest.name, latest))
        except Exception as e:
            logger.error(f"Batch anonymize failed for {doc_id}: {e}")
            results.append(BatchAnonymizeResult(
                doc_id=doc_id, success=False, error=str(e),
            ))

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
