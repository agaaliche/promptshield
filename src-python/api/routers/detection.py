"""PII detection, re-detection, and detection progress."""

from __future__ import annotations

import logging
import time as _time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _PydanticBaseModel, Field

from core.config import config
from core.detection.noise_filters import has_legal_suffix as _has_legal_suffix
from models.schemas import (
    BBox,
    DocumentStatus,
    PIIRegion,
)
from api.deps import (
    cleanup_stale_progress,
    detection_progress,
    get_active_llm_engine,
    get_doc,
    save_doc,
    acquire_detection_lock,
    release_detection_lock,
    config_override,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["detection"])


@router.get("/documents/{doc_id}/detection-progress")
async def get_detection_progress(doc_id: str) -> dict[str, Any]:
    """Return real-time detection progress for a document."""
    # Evict stale entries on each poll
    cleanup_stale_progress()
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
async def detect_pii(doc_id: str) -> dict[str, Any]:
    """Run PII detection on all pages of a document."""
    import asyncio
    import traceback

    doc = get_doc(doc_id)  # 404 before heavy imports

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")

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

        def _run_detection() -> list[PIIRegion]:
            """Run detection on all pages in-thread and update progress."""
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
        all_regions = await asyncio.to_thread(_run_detection)

        # Propagate: if text was detected on one page, flag it on every
        # other page where it also appears.
        doc.regions = propagate_regions_across_pages(all_regions, doc.pages)

        # Final sweep: drop any ORG region with digit-only or very short text
        # Exception: numbered companies with legal suffixes (e.g., "9169270 Canada Inc.")
        from models.schemas import PIIType as _PIIType
        _org_before = len(doc.regions)
        doc.regions = [
            r for r in doc.regions
            if not (
                r.pii_type == _PIIType.ORG
                and (
                    len(r.text.strip()) <= 2
                    or r.text.strip().isdigit()
                    or (
                        r.text.strip()
                        and r.text.strip()[0].isdigit()
                        and not _has_legal_suffix(r.text)
                    )
                )
            )
        ]
        _org_swept = _org_before - len(doc.regions)
        if _org_swept:
            logger.info(f"Final ORG sweep removed {_org_swept} digit/short ORG(s)")

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
    finally:
        release_detection_lock()


class RedetectRequest(_PydanticBaseModel):
    """Request body for the redetect (autodetect) endpoint."""
    # M10: Add ge/le bounds to confidence_threshold
    confidence_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    page_number: Optional[int] = None  # None = all pages
    regex_enabled: bool = True
    ner_enabled: bool = True
    llm_detection_enabled: bool = True
    regex_types: Optional[list[str]] = None   # None = all types; e.g. ["EMAIL", "SSN"]
    ner_types: Optional[list[str]] = None     # None = all types; e.g. ["PERSON", "ORG"]
    blacklist_terms: Optional[list[str]] = None  # terms to search for (highest priority)
    blacklist_action: str = "none"               # "none" | "tokenize" | "remove"


@router.post("/documents/{doc_id}/redetect")
async def redetect_pii(doc_id: str, body: RedetectRequest) -> dict[str, Any]:
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

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages, _bbox_overlap_area, _bbox_area

        # Thread-safe config override for this detection run
        with config_override(
            confidence_threshold=body.confidence_threshold,
            regex_enabled=body.regex_enabled,
            ner_enabled=body.ner_enabled,
            llm_detection_enabled=body.llm_detection_enabled,
            regex_types=body.regex_types,
            ner_types=body.ner_types,
        ):
            engine = get_active_llm_engine()

            # Determine which pages to scan
            pages_to_scan = doc.pages
            if body.page_number is not None:
                pages_to_scan = [p for p in doc.pages if p.page_number == body.page_number]
                if not pages_to_scan:
                    raise HTTPException(404, detail=f"Page {body.page_number} not found")

            total_pages = len(pages_to_scan)

            # Initialize progress tracker (same format as initial detect)
            detection_progress[doc_id] = {
                "doc_id": doc_id,
                "status": "running",
                "current_page": 0,
                "total_pages": total_pages,
                "pages_done": 0,
                "regions_found": 0,
                "elapsed_seconds": 0.0,
                "page_statuses": [
                    {"page": p.page_number, "status": "pending", "regions": 0}
                    for p in pages_to_scan
                ],
                "_started_at": _time.time(),
            }

            def _run_redetection() -> list[PIIRegion]:
                """Run re-detection on selected pages in-thread."""
                results: list[PIIRegion] = []
                progress = detection_progress[doc_id]
                for idx, page in enumerate(pages_to_scan):
                    progress["current_page"] = page.page_number
                    progress["page_statuses"][idx]["status"] = "running"
                    progress["elapsed_seconds"] = _time.time() - progress["_started_at"]

                    detected = detect_pii_on_page(page, llm_engine=engine)
                    results.extend(detected)

                    progress["page_statuses"][idx]["status"] = "done"
                    progress["page_statuses"][idx]["regions"] = len(detected)
                    progress["pages_done"] = idx + 1
                    progress["regions_found"] = len(results)
                    progress["elapsed_seconds"] = _time.time() - progress["_started_at"]
                return results

            new_regions = await asyncio.to_thread(_run_redetection)

        # ── Blacklist: text-search for user-specified terms (highest priority) ──
        blacklist_created = 0
        if body.blacklist_terms:
            from core.detection.pipeline import _compute_block_offsets
            import uuid as _uuid
            from models.schemas import PIIType as _PIIType, DetectionSource as _DetSource, RegionAction as _RAct

            bl_action_map = {"tokenize": _RAct.TOKENIZE, "remove": _RAct.REMOVE}
            bl_target_action: _RAct | None = bl_action_map.get(body.blacklist_action)

            # Deduplicate terms (case-insensitive)
            _bl_seen: set[str] = set()
            bl_terms: list[str] = []
            for t in body.blacklist_terms:
                tc = t.strip()
                tl = tc.lower()
                if tc and tl not in _bl_seen:
                    _bl_seen.add(tl)
                    bl_terms.append(tc)

            bl_regions: list[PIIRegion] = []
            for page in pages_to_scan:
                ft = page.full_text
                if not ft:
                    continue
                ft_lower = ft.lower()
                block_offsets = _compute_block_offsets(page.text_blocks, ft)

                for needle in bl_terms:
                    nl = needle.lower()
                    nlen = len(nl)
                    if nlen == 0:
                        continue
                    pos = 0
                    while True:
                        idx = ft_lower.find(nl, pos)
                        if idx == -1:
                            break
                        pos = idx + 1
                        m_end = idx + nlen

                        # Map char range → bbox
                        hits = [blk for cs, ce, blk in block_offsets if ce > idx and cs < m_end]
                        if not hits:
                            continue
                        bx0 = max(0.0, min(b.bbox.x0 for b in hits))
                        by0 = max(0.0, min(b.bbox.y0 for b in hits))
                        bx1 = min(page.width, max(b.bbox.x1 for b in hits))
                        by1 = min(page.height, max(b.bbox.y1 for b in hits))

                        r = PIIRegion(
                            page_number=page.page_number,
                            bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                                      x1=round(bx1, 2), y1=round(by1, 2)),
                            text=ft[idx:m_end],
                            pii_type=_PIIType.CUSTOM,
                            confidence=1.0,
                            source=_DetSource.MANUAL,
                            action=bl_target_action if bl_target_action else _RAct.PENDING,
                            char_start=idx,
                            char_end=m_end,
                        )
                        r.id = _uuid.uuid4().hex[:12]
                        bl_regions.append(r)

            blacklist_created = len(bl_regions)
            # Prepend blacklist regions so they get highest priority in merge
            new_regions = bl_regions + new_regions
            if blacklist_created:
                logger.info("Blacklist: %d regions from %d terms", blacklist_created, len(bl_terms))

        # ── Merge new detections into existing regions ──
        scanned_pages = {p.page_number for p in pages_to_scan}
        existing_on_scanned = [r for r in doc.regions if r.page_number in scanned_pages]
        existing_other = [r for r in doc.regions if r.page_number not in scanned_pages]

        # Build set of PII types that were explicitly excluded by the user
        # so we can remove stale regions of those types from previous runs.
        _regex_tab_types = {"EMAIL", "PHONE", "SSN", "CREDIT_CARD", "IBAN", "DATE",
                            "IP_ADDRESS", "PASSPORT", "DRIVER_LICENSE", "ADDRESS"}
        _ner_tab_types = {"PERSON", "ORG", "LOCATION", "CUSTOM"}
        excluded_types: set[str] = set()
        if body.regex_enabled and body.regex_types is not None:
            excluded_types |= _regex_tab_types - set(body.regex_types)
        if not body.regex_enabled:
            excluded_types |= _regex_tab_types
        if body.ner_enabled and body.ner_types is not None:
            excluded_types |= _ner_tab_types - set(body.ner_types)
        if not body.ner_enabled:
            excluded_types |= _ner_tab_types

        # Drop existing regions whose type was explicitly excluded
        # (but never drop MANUAL regions — e.g. blacklist or user-drawn)
        if excluded_types:
            from models.schemas import DetectionSource as _DetSourceFilter
            existing_on_scanned = [
                r for r in existing_on_scanned
                if r.source == _DetSourceFilter.MANUAL
                or (r.pii_type.value if hasattr(r.pii_type, 'value') else str(r.pii_type)) not in excluded_types
            ]

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

        newly_added_ids: set[str] = set()
        for ni, nr in enumerate(new_regions):
            if ni not in updated_indices:
                existing_on_scanned.append(nr)
                newly_added_ids.add(nr.id)
                added_count += 1

        # ── Prune stale auto-detected regions ──
        # Remove old auto-detected regions that are still PENDING and
        # had no matching new detection (i.e. the improved detection no
        # longer flags them).  Regions that the user acted on (REMOVE,
        # TOKENIZE, CANCEL) or that were manually created are preserved.
        from models.schemas import RegionAction, DetectionSource
        pruned = []
        removed_count = 0
        for r in existing_on_scanned:
            if r.id in matched_existing_ids:
                # Was matched (updated) by a new detection — keep
                pruned.append(r)
            elif r.id in newly_added_ids:
                # Newly added this run — keep
                pruned.append(r)
            elif r.action != RegionAction.PENDING:
                # User already acted on it — keep
                pruned.append(r)
            elif r.source == DetectionSource.MANUAL:
                # Manually created — keep
                pruned.append(r)
            else:
                # Old auto-detected, still PENDING, no new match — remove
                removed_count += 1
                logger.debug(
                    "Pruning stale region %s: [%s] '%s' (source=%s)",
                    r.id, r.pii_type, r.text[:40] if r.text else "", r.source,
                )
        existing_on_scanned = pruned

        merged_regions = existing_other + existing_on_scanned

        # Propagate newly detected text across all pages
        all_regions = propagate_regions_across_pages(merged_regions, doc.pages)

        # Post-propagation: strip excluded types from the scanned pages
        # (propagation may re-create them from templates on other pages)
        # Never strip MANUAL regions (blacklist / user-drawn).
        if excluded_types:
            all_regions = [
                r for r in all_regions
                if r.source == DetectionSource.MANUAL
                or r.page_number not in scanned_pages
                or (r.pii_type.value if hasattr(r.pii_type, 'value') else str(r.pii_type)) not in excluded_types
            ]

        doc.regions = all_regions

        # Final sweep: drop any ORG region with digit-only or very short text
        # Exception: numbered companies with legal suffixes (e.g., "9169270 Canada Inc.")
        from models.schemas import PIIType as _PIIType
        _org_before_r = len(doc.regions)
        doc.regions = [
            r for r in doc.regions
            if not (
                r.pii_type == _PIIType.ORG
                and (
                    len(r.text.strip()) <= 2
                    or r.text.strip().isdigit()
                    or (
                        r.text.strip()
                        and r.text.strip()[0].isdigit()
                        and not _has_legal_suffix(r.text)
                    )
                )
            )
        ]
        _org_swept_r = _org_before_r - len(doc.regions)
        if _org_swept_r:
            logger.info(f"Redetect: final ORG sweep removed {_org_swept_r} digit/short ORG(s)")

        doc.status = DocumentStatus.REVIEWING
        save_doc(doc)

        # Mark progress as complete
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["regions_found"] = len(doc.regions)
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        logger.info(
            f"Redetect for '{doc.original_filename}' "
            f"(threshold={body.confidence_threshold}, pages={body.page_number or 'all'}): "
            f"{added_count} added, {updated_count} updated, {removed_count} pruned, "
            f"{len(doc.regions)} total"
        )

        return {
            "doc_id": doc_id,
            "added": added_count,
            "updated": updated_count,
            "removed": removed_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Redetect failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Redetect failed. Check server logs for details.")
    finally:
        release_detection_lock()


@router.post("/documents/{doc_id}/reset-detection")
async def reset_detection(doc_id: str) -> dict[str, Any]:
    """Clear ALL regions for a document and re-run fresh detection from scratch.

    Unlike ``/redetect`` (which merges), this wipes every region — including
    user-acted ones — and runs the detection pipeline as if the document had
    just been uploaded.  Use this when persisted data from an older detection
    run is corrupt or stale.
    """
    import asyncio
    import traceback

    doc = get_doc(doc_id)

    if not acquire_detection_lock(doc_id):
        raise HTTPException(409, detail="Detection already in progress. Please wait.")

    try:
        from core.detection.pipeline import detect_pii_on_page, propagate_regions_across_pages

        old_count = len(doc.regions)
        doc.status = DocumentStatus.DETECTING
        doc.regions = []

        engine = get_active_llm_engine()
        total_pages = len(doc.pages)

        detection_progress[doc_id] = {
            "doc_id": doc_id,
            "status": "running",
            "current_page": 0,
            "total_pages": total_pages,
            "pages_done": 0,
            "regions_found": 0,
            "elapsed_seconds": 0.0,
            "page_statuses": [
                {"page": p.page_number, "status": "pending", "regions": 0}
                for p in doc.pages
            ],
            "_started_at": _time.time(),
        }

        def _run() -> list[PIIRegion]:
            """Run fresh detection on all pages in-thread."""
            all_regions: list[PIIRegion] = []
            progress = detection_progress[doc_id]
            for idx, page in enumerate(doc.pages):
                progress["current_page"] = page.page_number
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

        all_regions = await asyncio.to_thread(_run)
        doc.regions = propagate_regions_across_pages(all_regions, doc.pages)
        doc.status = DocumentStatus.REVIEWING
        save_doc(doc)

        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "complete"
            detection_progress[doc_id]["regions_found"] = len(doc.regions)
            detection_progress[doc_id]["elapsed_seconds"] = (
                _time.time() - detection_progress[doc_id].get("_started_at", _time.time())
            )

        logger.info(
            "Reset detection for '%s': cleared %d old regions, found %d fresh",
            doc.original_filename, old_count, len(doc.regions),
        )

        return {
            "doc_id": doc_id,
            "cleared": old_count,
            "total_regions": len(doc.regions),
            "regions": [r.model_dump(mode="json") for r in doc.regions],
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Reset detection failed: {e}\n{tb}")
        if doc_id in detection_progress:
            detection_progress[doc_id]["status"] = "error"
            detection_progress[doc_id]["error"] = str(e)
        raise HTTPException(500, detail="Reset detection failed. Check server logs for details.")
    finally:
        release_detection_lock()


@router.get("/documents/{doc_id}/regions")
async def get_regions(doc_id: str, page_number: Optional[int] = None) -> list[dict[str, Any]]:
    """Get detected PII regions, optionally filtered by page."""
    doc = get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    return [r.model_dump(mode="json") for r in regions]
