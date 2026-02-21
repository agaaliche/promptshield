"""PII region CRUD, batch operations, highlight-all, and reanalysis."""

from __future__ import annotations

import asyncio
import logging
import unicodedata
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _PydanticBaseModel

from models.schemas import (
    BatchActionRequest,
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    RegionAction,
    RegionActionRequest,
)
from api.deps import get_doc, save_doc, _clamp_bbox

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["regions"])


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}/debug-detections")
async def debug_detections(doc_id: str, page_number: Optional[int] = None) -> dict[str, Any]:
    """Debug endpoint — shows every detection with type, confidence, source, text."""
    doc = get_doc(doc_id)
    regions = doc.regions
    if page_number is not None:
        regions = [r for r in regions if r.page_number == page_number]
    summary = []
    for r in regions:
        summary.append({
            "page": r.page_number,
            "type": r.pii_type.value if hasattr(r.pii_type, "value") else str(r.pii_type),
            "confidence": round(r.confidence, 3),
            "source": r.source.value if hasattr(r.source, "value") else str(r.source),
            "text": r.text[:80],
        })
    summary.sort(key=lambda x: (-x["confidence"], x["type"]))
    return {"total": len(summary), "regions": summary}


@router.get("/documents/{doc_id}/debug-page-text/{page_number}")
async def debug_page_text(doc_id: str, page_number: int) -> dict[str, Any]:
    """Debug endpoint — shows the extracted full_text for a page."""
    doc = get_doc(doc_id)
    if page_number < 1 or page_number > doc.page_count:
        raise HTTPException(400, f"Invalid page {page_number}")
    page = doc.pages[page_number - 1]
    return {
        "page_number": page_number,
        "full_text": page.full_text,
        "text_blocks_count": len(page.text_blocks),
        "text_block_samples": [
            {"text": b.text, "bbox": [b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1]}
            for b in page.text_blocks[-20:]  # last 20 blocks (likely footer)
        ],
    }


# ---------------------------------------------------------------------------
# Single-region mutations
# ---------------------------------------------------------------------------

@router.put("/documents/{doc_id}/regions/{region_id}/action")
async def set_region_action(doc_id: str, region_id: str, req: RegionActionRequest) -> dict[str, str]:
    """Set the action for a specific PII region (and linked siblings)."""
    doc = get_doc(doc_id)
    target = None
    for region in doc.regions:
        if region.id == region_id:
            target = region
            region.action = req.action
            break
    if target is None:
        raise HTTPException(404, f"Region '{region_id}' not found")
    # Propagate to linked siblings
    if target.linked_group:
        for region in doc.regions:
            if region.linked_group == target.linked_group:
                region.action = req.action
    save_doc(doc)
    return {"status": "ok", "region_id": region_id, "action": req.action.value}


@router.delete("/documents/{doc_id}/regions/{region_id}")
async def delete_region(doc_id: str, region_id: str) -> dict[str, str]:
    """Delete a PII region (and linked siblings) from the document."""
    doc = get_doc(doc_id)
    # Find linked_group before deletion
    target = next((r for r in doc.regions if r.id == region_id), None)
    if target is None:
        raise HTTPException(404, f"Region '{region_id}' not found")
    grp = target.linked_group
    if grp:
        doc.regions = [r for r in doc.regions if r.linked_group != grp]
    else:
        doc.regions = [r for r in doc.regions if r.id != region_id]
    save_doc(doc)
    return {"status": "ok", "region_id": region_id}


@router.put("/documents/{doc_id}/regions/{region_id}/bbox")
async def update_region_bbox(doc_id: str, region_id: str, bbox: BBox) -> dict[str, str]:
    """Update the bounding box of a PII region (move / resize)."""
    doc = get_doc(doc_id)
    # Find the page dimensions for clamping
    page_map = {p.page_number: p for p in doc.pages}
    for region in doc.regions:
        if region.id == region_id:
            pd = page_map.get(region.page_number)
            if pd is not None:
                bbox = _clamp_bbox(bbox, pd.width, pd.height)
            region.bbox = bbox
            save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


class UpdateLabelRequest(_PydanticBaseModel):
    pii_type: PIIType


@router.put("/documents/{doc_id}/regions/{region_id}/label")
async def update_region_label(doc_id: str, region_id: str, req: UpdateLabelRequest) -> dict[str, Any]:
    """Update the PII type label of a region and all same-text siblings."""
    doc = get_doc(doc_id)
    target = None
    for region in doc.regions:
        if region.id == region_id:
            target = region
            break
    if target is None:
        raise HTTPException(404, f"Region '{region_id}' not found")

    old_text = target.text.strip().lower()
    target.pii_type = req.pii_type
    updated: list[dict[str, str]] = [{"id": region_id, "pii_type": req.pii_type.value if hasattr(req.pii_type, 'value') else str(req.pii_type)}]

    # Propagate to all regions with the same text
    if old_text:
        for region in doc.regions:
            if region.id != region_id and region.text.strip().lower() == old_text:
                region.pii_type = req.pii_type
                updated.append({"id": region.id, "pii_type": updated[0]["pii_type"]})

    save_doc(doc)
    return {"status": "ok", "updated": updated}


class UpdateTextRequest(_PydanticBaseModel):
    text: str


@router.put("/documents/{doc_id}/regions/{region_id}/text")
async def update_region_text(doc_id: str, region_id: str, req: UpdateTextRequest) -> dict[str, Any]:
    """Update the detected text content of a region and all same-text siblings."""
    doc = get_doc(doc_id)
    target = None
    for region in doc.regions:
        if region.id == region_id:
            target = region
            break
    if target is None:
        raise HTTPException(404, f"Region '{region_id}' not found")

    old_text = target.text.strip().lower()
    target.text = req.text
    updated: list[dict[str, str]] = [{"id": region_id, "text": req.text}]

    # Propagate to all regions with the same text
    if old_text:
        for region in doc.regions:
            if region.id != region_id and region.text.strip().lower() == old_text:
                region.text = req.text
                updated.append({"id": region.id, "text": req.text})

    save_doc(doc)
    return {"status": "ok", "updated": updated}


@router.post("/documents/{doc_id}/regions/{region_id}/reanalyze")
async def reanalyze_region(doc_id: str, region_id: str) -> dict[str, Any]:
    """Re-analyze the content under a region's bounding box."""
    from core.detection.pipeline import reanalyze_bbox
    from core.llm.engine import llm_engine

    doc = get_doc(doc_id)
    region = None
    for r in doc.regions:
        if r.id == region_id:
            region = r
            break
    if region is None:
        raise HTTPException(404, f"Region '{region_id}' not found")

    page_data = None
    for p in doc.pages:
        if p.page_number == region.page_number:
            page_data = p
            break
    if page_data is None:
        raise HTTPException(400, f"Page {region.page_number} data not available")

    engine = llm_engine if llm_engine.is_loaded() else None
    # H5: reanalyze_bbox is CPU-bound; run in a thread to avoid blocking the event loop
    try:
        result = await asyncio.to_thread(reanalyze_bbox, page_data, region.bbox, llm_engine=engine)
    except Exception as e:
        logger.exception("reanalyze_bbox failed for region %s", region_id)
        raise HTTPException(500, f"Reanalysis failed: {e}")

    region.text = result["text"] or region.text
    if result["confidence"] > 0:
        region.pii_type = result["pii_type"]
        region.confidence = result["confidence"]
        region.source = result["source"]

    save_doc(doc)

    return {
        "region_id": region_id,
        "text": region.text,
        "pii_type": region.pii_type if isinstance(region.pii_type, str) else region.pii_type.value,
        "confidence": float(region.confidence),
        "source": region.source if isinstance(region.source, str) else region.source.value,
    }


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

@router.put("/documents/{doc_id}/regions/batch-action")
async def batch_region_action(doc_id: str, req: BatchActionRequest) -> dict[str, Any]:
    """Apply an action to multiple regions at once."""
    doc = get_doc(doc_id)
    region_map = {r.id: r for r in doc.regions}
    updated = 0
    for rid in req.region_ids:
        if rid in region_map:
            region_map[rid].action = req.action
            updated += 1
    save_doc(doc)
    return {"status": "ok", "updated": updated}


@router.post("/documents/{doc_id}/regions/batch-delete")
async def batch_delete_regions(doc_id: str, req: BatchActionRequest) -> dict[str, Any]:
    """Delete multiple regions at once."""
    doc = get_doc(doc_id)
    ids_to_delete = set(req.region_ids)
    original_len = len(doc.regions)
    doc.regions = [r for r in doc.regions if r.id not in ids_to_delete]
    deleted = original_len - len(doc.regions)
    save_doc(doc)
    return {"status": "ok", "deleted": deleted}


@router.post("/documents/{doc_id}/regions/add")
async def add_manual_region(doc_id: str, region: PIIRegion) -> dict[str, Any]:
    """Add a manually selected PII region, extract overlapping text, and
    create sibling regions for all other occurrences of the same text."""
    doc = get_doc(doc_id)
    # H4: Always generate server-side ID — never trust client-provided IDs
    region.id = uuid.uuid4().hex[:12]
    region.source = "MANUAL"
    # Clamp to page bounds
    page_map = {p.page_number: p for p in doc.pages}
    pd = page_map.get(region.page_number)
    if pd is not None:
        region.bbox = _clamp_bbox(region.bbox, pd.width, pd.height)

    # Extract real text under the bbox from text blocks.
    # We require the centre of each word to fall inside the drawn region so
    # that a wide selection across empty space doesn't capture distant words.
    # After extraction, shrink the region bbox to tightly fit matched blocks.
    if pd is not None:
        matched_blocks: list[Any] = []
        rx0, ry0, rx1, ry1 = (
            region.bbox.x0, region.bbox.y0, region.bbox.x1, region.bbox.y1,
        )
        for block in pd.text_blocks:
            bb = block.bbox
            cx = (bb.x0 + bb.x1) / 2
            cy = (bb.y0 + bb.y1) / 2
            if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                matched_blocks.append(block)

        # Column detection: sort blocks by horizontal centre and find
        # the largest gap.  If it exceeds a threshold we split into two
        # column groups and keep the one closest to the drawn region
        # centre.  This prevents a wide draw from merging text across
        # columns that happen to sit at the same vertical position.
        if matched_blocks:
            avg_h = sum(b.bbox.y1 - b.bbox.y0 for b in matched_blocks) / len(matched_blocks)

            cx_sorted = sorted(
                matched_blocks,
                key=lambda b: (b.bbox.x0 + b.bbox.x1) / 2,
            )

            best = cx_sorted  # default: keep all
            if len(cx_sorted) > 1:
                gaps: list[tuple[float, int]] = []
                for i in range(1, len(cx_sorted)):
                    prev_cx = (cx_sorted[i - 1].bbox.x0 + cx_sorted[i - 1].bbox.x1) / 2
                    cur_cx = (cx_sorted[i].bbox.x0 + cx_sorted[i].bbox.x1) / 2
                    gaps.append((cur_cx - prev_cx, i))

                max_gap, split_idx = max(gaps, key=lambda t: t[0])

                # Only split when the gap is substantial (> 5× avg word
                # height).  This avoids splitting words within the same
                # column that simply differ in x-centre.
                if max_gap > avg_h * 5:
                    group_a = cx_sorted[:split_idx]
                    group_b = cx_sorted[split_idx:]
                    draw_cx = (rx0 + rx1) / 2
                    cx_a = sum((b.bbox.x0 + b.bbox.x1) / 2 for b in group_a) / len(group_a)
                    cx_b = sum((b.bbox.x0 + b.bbox.x1) / 2 for b in group_b) / len(group_b)
                    best = group_a if abs(cx_a - draw_cx) <= abs(cx_b - draw_cx) else group_b

            best.sort(key=lambda b: (b.bbox.y0, b.bbox.x0))
            region.text = " ".join(b.text for b in best).strip()
            # Snap bbox to the union of the chosen group
            region.bbox = BBox(
                x0=round(min(b.bbox.x0 for b in best), 2),
                y0=round(min(b.bbox.y0 for b in best), 2),
                x1=round(max(b.bbox.x1 for b in best), 2),
                y1=round(max(b.bbox.y1 for b in best), 2),
            )

    # ── Dedup guard: if an existing (non-cancelled) region on the same page
    # already has the same normalised text and overlaps the same y-band, reuse it
    # rather than creating a duplicate.  We use y-range overlap (not full bbox IoU)
    # because auto-detected regions and manually-snapped regions compute bboxes via
    # different methods and may have zero x/area intersection for the same text.
    #
    # We also reuse when the new text is a substring of an existing region's text
    # (or vice versa) AND the bboxes have real x+y intersection — e.g. the user
    # draws "A129980" inside an auto-detected "publique n° A129980" region.
    region_norm = _normalize(region.text)
    existing_match: Any = None
    if region_norm:
        for er in doc.regions:
            if er.action == RegionAction.CANCEL or er.page_number != region.page_number:
                continue
            er_norm = _normalize(er.text)
            # Case 1: exact text match + y-band overlap
            if er_norm == region_norm:
                if er.bbox.y0 <= region.bbox.y1 and er.bbox.y1 >= region.bbox.y0:
                    existing_match = er
                    break
            # Case 2: the NEW text is contained within an EXISTING region's text
            # + real bbox intersection → reuse the bigger existing region.
            # We intentionally do NOT match when the existing text is a substring
            # of the new text (er_norm in region_norm), because that would
            # silently discard the user's broader selection in favour of a
            # shorter auto-detected region (e.g. user draws "Club Nautique
            # Jacques-Cartier", existing has "Nautique Jacques-Cartier" →
            # user would lose "Club").
            elif er_norm and region_norm in er_norm:
                ix0 = max(region.bbox.x0, er.bbox.x0)
                iy0 = max(region.bbox.y0, er.bbox.y0)
                ix1 = min(region.bbox.x1, er.bbox.x1)
                iy1 = min(region.bbox.y1, er.bbox.y1)
                if ix0 < ix1 and iy0 < iy1:
                    existing_match = er
                    break

    if existing_match is not None:
        # Reuse the existing region — update its pii_type if the user picked
        # a different one, then run highlight-all against it.
        if existing_match.pii_type != region.pii_type:
            existing_match.pii_type = region.pii_type
            save_doc(doc)
        new_regions_json: list[dict] = []
        all_ids: list[str] = [existing_match.id]
        cancelled_ids_list: list[str] = []
        if existing_match.text and existing_match.text != "[manual selection]":
            try:
                result = _highlight_all_impl(
                    doc_id, HighlightAllRequest(region_id=existing_match.id),
                )
                new_regions_json = result.get("new_regions", [])
                all_ids = result.get("all_ids", [existing_match.id])
                cancelled_ids_list = result.get("cancelled_ids", [])
            except Exception as e:
                logger.warning("Auto highlight-all after manual add (reuse) failed: %s", e)
        return {
            "status": "ok",
            "region_id": existing_match.id,
            "text": existing_match.text,
            "pii_type": existing_match.pii_type.value if hasattr(existing_match.pii_type, "value") else str(existing_match.pii_type),
            "bbox": existing_match.bbox.model_dump(mode="json"),
            "new_regions": new_regions_json,
            "all_ids": all_ids,
            "cancelled_ids": cancelled_ids_list,
        }

    doc.regions.append(region)
    save_doc(doc)

    # If meaningful text was found, highlight all occurrences across the doc
    new_regions_json: list[dict] = []
    all_ids: list[str] = [region.id]
    cancelled_ids_list: list[str] = []
    if region.text and region.text != "[manual selection]":
        try:
            result = _highlight_all_impl(
                doc_id, HighlightAllRequest(region_id=region.id),
            )
            new_regions_json = result.get("new_regions", [])
            all_ids = result.get("all_ids", [region.id])
            cancelled_ids_list = result.get("cancelled_ids", [])
        except Exception as e:
            logger.warning("Auto highlight-all after manual add failed: %s", e)

    return {
        "status": "ok",
        "region_id": region.id,
        "text": region.text,
        "pii_type": region.pii_type.value if hasattr(region.pii_type, "value") else str(region.pii_type),
        "bbox": region.bbox.model_dump(mode="json"),
        "new_regions": new_regions_json,
        "all_ids": all_ids,
        "cancelled_ids": cancelled_ids_list,
    }


# ---------------------------------------------------------------------------
# Blacklist — batch text search → create/flag regions
# ---------------------------------------------------------------------------

class BlacklistRequest(_PydanticBaseModel):
    terms: list[str]
    action: str = "none"        # "none" | "tokenize" | "remove"
    page_number: Optional[int] = None  # None = all pages


@router.post("/documents/{doc_id}/regions/blacklist")
async def apply_blacklist(doc_id: str, req: BlacklistRequest) -> dict[str, Any]:
    """Search the document for each term and create MANUAL regions for matches.

    If a term overlaps an existing region, optionally flag that region for
    tokenization or removal instead of creating a duplicate.
    """
    import traceback
    try:
        return _blacklist_impl(doc_id, req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("blacklist error: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, detail="Internal server error")


def _blacklist_impl(doc_id: str, req: BlacklistRequest) -> dict[str, Any]:
    """Core implementation of the blacklist feature."""
    doc = get_doc(doc_id)

    # Determine target action
    action_map = {
        "tokenize": RegionAction.TOKENIZE,
        "remove": RegionAction.REMOVE,
    }
    target_action: RegionAction | None = action_map.get(req.action)

    # Determine which pages to scan
    pages_to_scan = doc.pages
    if req.page_number is not None:
        pages_to_scan = [p for p in doc.pages if p.page_number == req.page_number]
        if not pages_to_scan:
            raise HTTPException(404, f"Page {req.page_number} not found")

    # Deduplicate and clean terms
    seen: set[str] = set()
    terms: list[str] = []
    for t in req.terms:
        t_clean = t.strip()
        t_lower = t_clean.lower()
        if t_clean and t_lower not in seen:
            seen.add(t_lower)
            terms.append(t_clean)

    if not terms:
        return {"created": 0, "flagged": 0, "regions": []}

    # Build existing-region lookup per page
    existing_spans: dict[int, list[tuple[float, float, float, float, str, str]]] = {}
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        existing_spans.setdefault(r.page_number, []).append(
            (r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1,
             r.text.strip().lower(), r.id)
        )

    from core.detection.pipeline import _compute_block_offsets

    created_regions: list[PIIRegion] = []
    flagged_ids: set[str] = set()

    for page in pages_to_scan:
        full_text = page.full_text
        if not full_text:
            continue

        block_offsets = _compute_block_offsets(page.text_blocks, full_text)

        # Build accent-stripped lowercase text + index map to originals.
        # NFD decomposes accented chars (é→e+combining-accent), then we
        # strip combining marks.  _n2o maps each position in the
        # stripped string back to the corresponding original char index.
        _nfd = unicodedata.normalize("NFD", full_text.lower())
        _norm_chars: list[str] = []
        _n2o: list[int] = []
        _seen = 0
        for ci in range(len(full_text)):
            clen = len(unicodedata.normalize("NFD", full_text[ci]))
            for _ in range(clen):
                if _seen < len(_nfd) and unicodedata.category(_nfd[_seen]) != "Mn":
                    _norm_chars.append(_nfd[_seen])
                    _n2o.append(ci)
                _seen += 1
        _n2o.append(len(full_text))  # sentinel
        full_norm = "".join(_norm_chars)

        for needle in terms:
            needle_norm = "".join(
                ch for ch in unicodedata.normalize("NFD", needle.lower())
                if unicodedata.category(ch) != "Mn"
            )
            needle_len = len(needle_norm)
            if needle_len == 0:
                continue

            # Find all accent-agnostic, case-insensitive occurrences
            search_start = 0
            while True:
                ni = full_norm.find(needle_norm, search_start)
                if ni == -1:
                    break
                search_start = ni + 1
                # Map normalized positions back to original text positions
                idx = _n2o[ni]
                match_end = _n2o[min(ni + needle_len, len(_n2o) - 1)]

                # Map char range → bounding box via text blocks
                hit_blocks = []
                for cs, ce, blk in block_offsets:
                    if ce <= idx:
                        continue
                    if cs >= match_end:
                        break
                    hit_blocks.append(blk)

                if not hit_blocks:
                    continue

                bx0 = min(b.bbox.x0 for b in hit_blocks)
                by0 = min(b.bbox.y0 for b in hit_blocks)
                bx1 = max(b.bbox.x1 for b in hit_blocks)
                by1 = max(b.bbox.y1 for b in hit_blocks)

                # Clamp to page bounds
                bx0 = max(0.0, min(bx0, page.width))
                by0 = max(0.0, min(by0, page.height))
                bx1 = max(0.0, min(bx1, page.width))
                by1 = max(0.0, min(by1, page.height))

                # Check if an existing region already covers this area
                page_existing = existing_spans.get(page.page_number, [])
                covered_region_id: str | None = None
                for ex0, ey0, ex1, ey1, _etxt, eid in page_existing:
                    ix0 = max(bx0, ex0)
                    iy0 = max(by0, ey0)
                    ix1 = min(bx1, ex1)
                    iy1 = min(by1, ey1)
                    if ix0 < ix1 and iy0 < iy1:
                        inter_area = (ix1 - ix0) * (iy1 - iy0)
                        new_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
                        if inter_area / new_area > _OVERLAP_COVERAGE_THRESHOLD:
                            covered_region_id = eid
                            break

                if covered_region_id:
                    # Already covered — optionally flag the existing region
                    if target_action and covered_region_id not in flagged_ids:
                        for r in doc.regions:
                            if r.id == covered_region_id:
                                r.action = target_action
                                flagged_ids.add(r.id)
                                break
                    continue

                # Create a new region
                matched_text = full_text[idx:match_end]
                region = PIIRegion(
                    page_number=page.page_number,
                    bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                              x1=round(bx1, 2), y1=round(by1, 2)),
                    text=matched_text,
                    pii_type=PIIType.CUSTOM,
                    confidence=1.0,
                    source=DetectionSource.MANUAL,
                    action=target_action if target_action else RegionAction.PENDING,
                    char_start=idx,
                    char_end=match_end,
                )
                region.id = uuid.uuid4().hex[:12]
                created_regions.append(region)
                doc.regions.append(region)
                existing_spans.setdefault(page.page_number, []).append(
                    (bx0, by0, bx1, by1, needle_lower, region.id)
                )

    save_doc(doc)

    return {
        "created": len(created_regions),
        "flagged": len(flagged_ids),
        "regions": [r.model_dump(mode="json") for r in doc.regions],
    }


# ---------------------------------------------------------------------------
# Highlight-all
# ---------------------------------------------------------------------------

class HighlightAllRequest(_PydanticBaseModel):
    region_id: str


@router.post("/documents/{doc_id}/regions/highlight-all")
async def highlight_all(doc_id: str, req: HighlightAllRequest) -> dict[str, Any]:
    """Find all occurrences of a region's text across every page and create
    new MANUAL regions for any that don't already have one."""
    import traceback
    try:
        return _highlight_all_impl(doc_id, req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"highlight-all error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Highlight-all helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize for fuzzy matching: lowercase, collapse whitespace, strip accents."""
    from core.text_utils import normalize_for_matching
    return normalize_for_matching(text)


def _fuzzy_ratio(a: str, b: str) -> float:
    """Quick similarity ratio between two strings (0..1)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


_FUZZY_THRESHOLD = 0.75  # 75% similarity for highlight-all matching
_OVERLAP_COVERAGE_THRESHOLD = 0.4  # 40% bbox intersection to consider "already covered"
_CHAR_OVERLAP_MIN_RATIO = 0.6  # 60% char-frequency overlap for fuzzy pre-filter


def _highlight_all_impl(doc_id: str, req: HighlightAllRequest) -> dict[str, Any]:
    """Core implementation of highlight-all — find and create regions for all
    occurrences of a region's text across every page."""
    doc = get_doc(doc_id)

    # Find the source region
    source_region = next((r for r in doc.regions if r.id == req.region_id), None)
    if source_region is None:
        raise HTTPException(404, "Region not found")

    needle = source_region.text.strip()
    needle_lower = needle.lower()
    needle_norm = _normalize(needle)
    if not needle_norm:
        return {"created": 0, "new_regions": [], "all_ids": [source_region.id]}

    # Gather existing region bboxes per page to avoid duplicates.
    existing_spans: dict[int, list[tuple[float, float, float, float, str]]] = {}
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        existing_spans.setdefault(r.page_number, []).append(
            (r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1, r.text.strip().lower())
        )

    new_regions: list[PIIRegion] = []
    cancelled_ids: set[str] = set()

    for page in doc.pages:
        full_text = page.full_text
        if not full_text:
            continue

        from core.detection.pipeline import _compute_block_offsets
        from core.detection.block_offsets import _char_offsets_to_line_bboxes, _char_offset_to_bbox
        block_offsets = _compute_block_offsets(page.text_blocks, full_text)

        # ---- Fuzzy sliding-window search for needle in full_text ----
        needle_len = len(needle_norm)
        full_norm = _normalize(full_text)

        # Build a mapping from normalized-string index → original char index.
        #
        # The chain is:
        #   full_norm position  (ws-collapsed, lower, accent-stripped)
        #       → tmp3 position  (same chars, NOT ws-collapsed; len == len(full_text))
        #       → tmp  position  (raw NFKD; longer because combining marks are present)
        #       → full_text position  (via nfkd_to_orig)
        #
        # Bug in previous code: _norm_chars[i] is a tmp3 index, but was fed
        # directly into nfkd_to_orig (indexed by NFKD positions).  After the
        # first accented char the two arrays diverge → wrong offsets → wrong
        # bboxes for regions with accented multi-word names.  Fix: build
        # tmp2_to_nfkd to bridge tmp3/tmp2 positions → NFKD positions.
        import unicodedata, re as _re
        tmp = unicodedata.normalize("NFKD", full_text)
        tmp3 = "".join(c for c in tmp if not unicodedata.combining(c)).lower()

        # tmp2_to_nfkd[i] = NFKD position corresponding to tmp2/tmp3 position i
        _tmp2_to_nfkd: list[int] = []
        _nfkd_i = 0
        for _c in tmp:
            if not unicodedata.combining(_c):
                _tmp2_to_nfkd.append(_nfkd_i)
            _nfkd_i += 1

        # nfkd_to_orig[j] = position in full_text for NFKD position j
        nfkd_to_orig: list[int] = []
        _ni = 0
        for _oi, _orig_c in enumerate(full_text):
            for _ in unicodedata.normalize("NFKD", _orig_c):
                nfkd_to_orig.append(_oi)
                _ni += 1

        # _norm_chars[i] = position in tmp3 that corresponds to full_norm[i]
        _norm_chars: list[int] = []
        in_space = False
        stripped_leading = False
        for ci, ch in enumerate(tmp3):
            is_ws = ch in (" ", "\t", "\n", "\r")
            if not stripped_leading and is_ws:
                continue
            if is_ws:
                if not in_space:
                    _norm_chars.append(ci)
                    in_space = True
            else:
                stripped_leading = True
                _norm_chars.append(ci)
                in_space = False

        def norm_idx_to_orig(ni_: int) -> int:
            """Map normalized-string index → original full_text index."""
            if ni_ < len(_norm_chars):
                tmp3_idx = _norm_chars[ni_]                    # position in tmp3 (== tmp2)
                if tmp3_idx < len(_tmp2_to_nfkd):
                    nfkd_idx = _tmp2_to_nfkd[tmp3_idx]        # position in NFKD (tmp)
                    if nfkd_idx < len(nfkd_to_orig):
                        return nfkd_to_orig[nfkd_idx]          # position in full_text
            return len(full_text)

        # Try exact normalized match first (fast path)
        search_start_n = 0
        matches: list[tuple[int, int]] = []

        while True:
            idx_n = full_norm.find(needle_norm, search_start_n)
            if idx_n == -1:
                break
            search_start_n = idx_n + 1
            orig_start = norm_idx_to_orig(idx_n)
            orig_end_idx = idx_n + needle_len
            orig_end = norm_idx_to_orig(orig_end_idx) if orig_end_idx < len(full_norm) else len(full_text)
            matches.append((orig_start, orig_end))

        # Also try fuzzy sliding window to catch OCR/encoding variations.
        # Only run when exact matching found nothing — apostrophe/quote variants
        # are now handled by normalize_for_matching so they hit the exact path.
        if needle_len >= 2 and len(matches) == 0:
            window = needle_len
            # Pre-compute needle character frequency for fast pre-filter
            from collections import Counter
            needle_freq = Counter(needle_norm)
            for tol in (0, 1, 2):
                wlen = window + tol
                if wlen > len(full_norm):
                    continue
                for si in range(len(full_norm) - wlen + 1):
                    chunk = full_norm[si : si + wlen]
                    # Fast char-frequency pre-filter: skip if character overlap is too low
                    chunk_freq = Counter(chunk)
                    shared = sum((needle_freq & chunk_freq).values())
                    if shared < needle_len * _CHAR_OVERLAP_MIN_RATIO:
                        continue
                    if _fuzzy_ratio(needle_norm, chunk) >= _FUZZY_THRESHOLD:
                        orig_start = norm_idx_to_orig(si)
                        orig_end = norm_idx_to_orig(si + wlen) if si + wlen < len(full_norm) else len(full_text)
                        if any(abs(orig_start - ms) < max(needle_len // 2, 2) for ms, _ in matches):
                            continue
                        matches.append((orig_start, orig_end))
                wlen = window - tol if tol > 0 else -1
                if wlen >= 2 and wlen <= len(full_norm):
                    for si in range(len(full_norm) - wlen + 1):
                        chunk = full_norm[si : si + wlen]
                        chunk_freq = Counter(chunk)
                        shared = sum((needle_freq & chunk_freq).values())
                        if shared < needle_len * _CHAR_OVERLAP_MIN_RATIO:
                            continue
                        if _fuzzy_ratio(needle_norm, chunk) >= _FUZZY_THRESHOLD:
                            orig_start = norm_idx_to_orig(si)
                            orig_end = norm_idx_to_orig(si + wlen) if si + wlen < len(full_norm) else len(full_text)
                            if any(abs(orig_start - ms) < max(needle_len // 2, 2) for ms, _ in matches):
                                continue
                            matches.append((orig_start, orig_end))

        for idx, match_end in matches:
            # Use per-line bbox splitting — same approach as propagation.py
            line_bboxes = _char_offsets_to_line_bboxes(idx, match_end, block_offsets)
            if not line_bboxes:
                single = _char_offset_to_bbox(idx, match_end, block_offsets)
                if single is None:
                    continue
                line_bboxes = [single]

            matched_text = full_text[idx:match_end]

            for lbbox in line_bboxes:
                bx0, by0, bx1, by1 = lbbox.x0, lbbox.y0, lbbox.x1, lbbox.y1

                # Clamp to page bounds
                bx0 = max(0.0, min(bx0, page.width))
                by0 = max(0.0, min(by0, page.height))
                bx1 = max(0.0, min(bx1, page.width))
                by1 = max(0.0, min(by1, page.height))

                page_existing = existing_spans.get(page.page_number, [])
                already_covered = False
                matched_text_norm = _normalize(matched_text)
                for ex0, ey0, ex1, ey1, etxt in page_existing:
                    # Same normalised text + y-ranges overlap → same occurrence.
                    # We intentionally DON'T require x/area overlap here because
                    # add_manual_region snaps bboxes via word-centre logic while
                    # _char_offsets_to_line_bboxes uses a different line-level
                    # method; the two can have zero bbox intersection for the same
                    # text, but they will always share the same y-range.
                    if _normalize(etxt) == matched_text_norm:
                        if ey0 <= by1 and ey1 >= by0:   # any y-overlap
                            already_covered = True
                            break
                        continue   # same text but different line → don't skip
                    # Different text: fall back to area-coverage threshold.
                    # BUT don't skip when the existing region's text is
                    # significantly shorter than the match — that means the
                    # existing region is a partial (e.g. auto-detected
                    # "Nautique Jacques-Cartier" inside the new match
                    # "Club Nautique Jacques-Cartier").  The new match
                    # represents a broader selection and must be created.
                    etxt_norm = _normalize(etxt)
                    if len(etxt_norm) < len(matched_text_norm) * 0.85:
                        continue
                    ix0 = max(bx0, ex0); iy0 = max(by0, ey0)
                    ix1 = min(bx1, ex1); iy1 = min(by1, ey1)
                    if ix0 < ix1 and iy0 < iy1:
                        inter_area = (ix1 - ix0) * (iy1 - iy0)
                        new_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
                        if inter_area / new_area > _OVERLAP_COVERAGE_THRESHOLD:
                            already_covered = True
                            break
                if already_covered:
                    continue

                # Cancel any existing regions whose text is a strict subset of
                # this match AND whose bbox intersects with the new region.  These
                # are partial auto-detections superseded by the broader match (e.g.
                # "Nautique Jacques-Cartier" cancelled when the new match is
                # "Club Nautique Jacques-Cartier").  Adjacent regions are safe
                # because they won't have a real bbox intersection.
                for _er in list(doc.regions):
                    if _er.action == RegionAction.CANCEL or _er.page_number != page.page_number:
                        continue
                    _er_norm = _normalize(_er.text)
                    if not _er_norm or _er_norm == matched_text_norm:
                        continue
                    if _er_norm not in matched_text_norm:
                        continue
                    _ix0 = max(bx0, _er.bbox.x0); _iy0 = max(by0, _er.bbox.y0)
                    _ix1 = min(bx1, _er.bbox.x1); _iy1 = min(by1, _er.bbox.y1)
                    if _ix0 < _ix1 and _iy0 < _iy1:
                        _er.action = RegionAction.CANCEL
                        cancelled_ids.add(_er.id)
                        # Remove from existing_spans so it no longer blocks
                        # future match iterations on this page
                        existing_spans[page.page_number] = [
                            _s for _s in existing_spans.get(page.page_number, [])
                            if not (abs(_s[0] - _er.bbox.x0) < 1.0
                                    and abs(_s[1] - _er.bbox.y0) < 1.0)
                        ]

                region = PIIRegion(
                    page_number=page.page_number,
                    bbox=BBox(x0=round(bx0, 2), y0=round(by0, 2),
                              x1=round(bx1, 2), y1=round(by1, 2)),
                    text=matched_text,
                    pii_type=source_region.pii_type,
                    confidence=source_region.confidence,
                    source=DetectionSource.MANUAL,
                    action=RegionAction.PENDING,
                    char_start=idx,
                    char_end=match_end,
                )
                new_regions.append(region)
                doc.regions.append(region)
                existing_spans.setdefault(page.page_number, []).append(
                    (bx0, by0, bx1, by1, needle_lower)
                )

    # Collect all matching region IDs (existing + new) using fuzzy match.
    # We require the texts to be approximately EQUAL (not just substring matches)
    # to avoid selecting pre-existing regions that merely CONTAIN the needle
    # (e.g. an existing "publique n° A129980" auto-detection getting pulled in
    # when the user just drew "A129980").
    new_ids = {r.id for r in new_regions}
    all_ids = []
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        r_norm = _normalize(r.text.strip())
        if not r_norm:
            continue
        # Keep the source region and any newly created siblings unconditionally,
        # then accept existing regions only when their text is similar in length
        # AND fuzzy-matches the needle (prevents false substring inclusions).
        if r.id == source_region.id or r.id in new_ids:
            all_ids.append(r.id)
        elif _fuzzy_ratio(needle_norm, r_norm) >= _FUZZY_THRESHOLD:
            all_ids.append(r.id)

    save_doc(doc)

    return {
        "created": len(new_regions),
        "new_regions": [r.model_dump(mode="json") for r in new_regions],
        "all_ids": all_ids,
        "cancelled_ids": list(cancelled_ids),
    }
