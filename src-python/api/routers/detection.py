"""PII detection, re-detection, and detection progress."""

from __future__ import annotations

import logging
import time as _time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _PydanticBaseModel

from core.config import config
from models.schemas import (
    DocumentStatus,
    PIIRegion,
)
from api.deps import (
    detection_progress,
    get_active_llm_engine,
    get_doc,
    save_doc,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["detection"])


@router.get("/documents/{doc_id}/detection-progress")
async def get_detection_progress(doc_id: str):
    """Return real-time detection progress for a document."""
    progress = detection_progress.get(doc_id)
    if progress is None:
        return {
            "doc_id": doc_id,
            "status": "idle",
            "current_page": 0,
            "total_pages": 0,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "page_statuses": [],
        }
    # Update elapsed time
    progress["elapsed_seconds"] = _time.time() - progress.get("_started_at", _time.time())
    # Return a clean copy (exclude internal keys)
    return {k: v for k, v in progress.items() if not k.startswith("_")}


@router.post("/documents/{doc_id}/detect")
async def detect_pii(doc_id: str):
    """Run PII detection on all pages of a document."""
    import asyncio
    import traceback

    doc = get_doc(doc_id)  # 404 before heavy imports

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages
        doc.status = DocumentStatus.DETECTING
        doc.regions = []

        engine = get_active_llm_engine()
        total_pages = len(doc.pages)

        # Initialize progress tracker
        detection_progress[doc_id] = {
            "doc_id": doc_id,
            "status": "running",
            "current_page": 0,
            "total_pages": total_pages,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "page_statuses": [
                {"page": i + 1, "status": "pending", "regions": 0}
                for i in range(total_pages)
            ],
            "_started_at": _time.time(),
        }

        def _run_detection():
            all_regions: list[PIIRegion] = []
            progress = detection_progress[doc_id]
            for idx, page in enumerate(doc.pages):
                progress["current_page"] = idx + 1
                progress["page_statuses"][idx]["status"] = "running"
                progress["elapsed_seconds"] = _time.time() - progress["_started_at"]

                regions = detect_pii_on_page(page, llm_engine=engine)
                all_regions.extend(regions)

                progress["page_statuses"][idx]["status"] = "done"
                progress["page_statuses"][idx]["regions"] = len(regions)
                progress["pages_done"] = idx + 1
                progress["regions_found"] = len(all_regions)
                progress["elapsed_seconds"] = _time.time() - progress["_started_at"]
            return all_regions

        # Run CPU-bound detection in a thread pool
        all_regions = await asyncio.get_event_loop().run_in_executor(None, _run_detection)

        # Propagate: if text was detected on one page, flag it on every
        # other page where it also appears.
        doc.regions = propagate_regions_across_pages(all_regions, doc.pages)

        doc.status = DocumentStatus.REVIEWING
        logger.info(f"Detection complete for '{doc.original_filename}': {len(doc.regions)} regions")

        save_doc(doc)

        # Mark progress as complete
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        return {
            "doc_id": doc_id,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Detection failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Detection failed. Check server logs for details.")


class RedetectRequest(_PydanticBaseModel):
    """Request body for the redetect (autodetect) endpoint."""
    confidence_threshold: float = 0.55
    page_number: Optional[int] = None  # None = all pages
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True


@router.post("/documents/{doc_id}/redetect")
async def redetect_pii(doc_id: str, body: RedetectRequest):
    """Re-run PII detection with custom fuzziness (confidence threshold).

    Merge strategy:
    - New regions (no significant bbox overlap with existing) → added.
    - Existing regions that overlap with a new detection → updated in place
      (text, pii_type, confidence, source refreshed) but action preserved.
    - Existing regions with no new match → kept untouched (never deleted).
    """
    import asyncio
    import traceback

    doc = get_doc(doc_id)  # 404 before heavy imports

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages, _bbox_overlap_area, _bbox_area

        # Temporarily override config thresholds for this detection run
        original_threshold = config.confidence_threshold
        original_regex = config.regex_enabled
        original_ner = config.ner_enabled
        original_llm = config.llm_detection_enabled
        try:
            config.confidence_threshold = body.confidence_threshold
            config.regex_enabled = body.regex_enabled
            config.ner_enabled = body.ner_enabled
            config.llm_detection_enabled = body.llm_detection_enabled

            engine = get_active_llm_engine()

            # Determine which pages to scan
            pages_to_scan = doc.pages
            if body.page_number is not None:
                pages_to_scan = [p for p in doc.pages if p.page_number == body.page_number]
                if not pages_to_scan:
                    raise HTTPException(404, detail=f"Page {body.page_number} not found")

            def _run_redetection():
                results: list[PIIRegion] = []
                for page in pages_to_scan:
                    detected = detect_pii_on_page(page, llm_engine=engine)
                    results.extend(detected)
                return results

            new_regions = await asyncio.get_event_loop().run_in_executor(None, _run_redetection)

        finally:
            config.confidence_threshold = original_threshold
            config.regex_enabled = original_regex
            config.ner_enabled = original_ner
            config.llm_detection_enabled = original_llm

        # ── Merge new detections into existing regions ──
        scanned_pages = {p.page_number for p in pages_to_scan}
        existing_on_scanned = [r for r in doc.regions if r.page_number in scanned_pages]
        existing_other = [r for r in doc.regions if r.page_number not in scanned_pages]

        OVERLAP_THRESHOLD = 0.50
        matched_existing_ids: set[str] = set()
        updated_indices: set[int] = set()
        added_count = 0
        updated_count = 0

        for ni, nr in enumerate(new_regions):
            nr_area = _bbox_area(nr.bbox)
            if nr_area <= 0:
                continue

            best_match = None
            best_iou = 0.0
            for er in existing_on_scanned:
                if er.page_number != nr.page_number or er.id in matched_existing_ids:
                    continue
                overlap = _bbox_overlap_area(nr.bbox, er.bbox)
                er_area = _bbox_area(er.bbox)
                if er_area <= 0:
                    continue
                union = nr_area + er_area - overlap
                iou = overlap / union if union > 0 else 0
                if iou > best_iou:
                    best_iou = iou
                    best_match = er

            if best_match and best_iou >= OVERLAP_THRESHOLD:
                best_match.bbox = nr.bbox
                best_match.text = nr.text
                best_match.pii_type = nr.pii_type
                best_match.confidence = nr.confidence
                best_match.source = nr.source
                best_match.char_start = nr.char_start
                best_match.char_end = nr.char_end
                matched_existing_ids.add(best_match.id)
                updated_indices.add(ni)
                updated_count += 1

        for ni, nr in enumerate(new_regions):
            if ni not in updated_indices:
                existing_on_scanned.append(nr)
                added_count += 1

        merged_regions = existing_other + existing_on_scanned

        # Propagate newly detected text across all pages
        doc.regions = propagate_regions_across_pages(merged_regions, doc.pages)

        doc.status = DocumentStatus.REVIEWING
        save_doc(doc)

        logger.info(
            f"Redetect for '{doc.original_filename}' "
            f"(threshold={body.confidence_threshold}, pages={body.page_number or 'all'}): "
            f"{added_count} added, {updated_count} updated, "
            f"{len(doc.regions)} total"
        )

        return {
            "doc_id": doc_id,
            "added": added_count,
            "updated": updated_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Redetect failed: {e}\n{tb}")
        raise HTTPException(500, detail="Redetect failed. Check server logs for details.")


@router.get("/documents/{doc_id}/regions")
async def get_regions(doc_id: str, page_number: Optional[int] = None):
    """Get detected PII regions, optionally filtered by page."""
    doc = get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    return [r.model_dump(mode="json") for r in regions]
