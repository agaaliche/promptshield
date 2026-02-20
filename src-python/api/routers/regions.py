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

    doc.regions.append(region)
    save_doc(doc)

    # If meaningful text was found, highlight all occurrences across the doc
    new_regions_json: list[dict] = []
    all_ids: list[str] = [region.id]
    if region.text and region.text != "[manual selection]":
        try:
            result = _highlight_all_impl(
                doc_id, HighlightAllRequest(region_id=region.id),
            )
            new_regions_json = result.get("new_regions", [])
            all_ids = result.get("all_ids", [region.id])
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
        import unicodedata, re as _re
        tmp = unicodedata.normalize("NFKD", full_text)
        tmp2 = "".join(c for c in tmp if not unicodedata.combining(c))
        tmp3 = tmp2.lower()

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

        # map from tmp3 index -> original full_text index
        orig_to_nfkd: list[int] = []
        nfkd_to_orig: list[int] = []
        ni = 0
        for oi_c, orig_c in enumerate(full_text):
            nfkd_of_c = unicodedata.normalize("NFKD", orig_c)
            orig_to_nfkd.append(ni)
            for _ in nfkd_of_c:
                nfkd_to_orig.append(oi_c)
                ni += 1

        def norm_idx_to_orig(ni_: int) -> int:
            """Map normalized string index to original full_text index."""
            if ni_ < len(_norm_chars):
                nfkd_idx = _norm_chars[ni_]
                if nfkd_idx < len(nfkd_to_orig):
                    return nfkd_to_orig[nfkd_idx]
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

        # Also try fuzzy sliding window to catch OCR variations
        # Only if exact matching found fewer than expected matches
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
                for ex0, ey0, ex1, ey1, etxt in page_existing:
                    ix0 = max(bx0, ex0)
                    iy0 = max(by0, ey0)
                    ix1 = min(bx1, ex1)
                    iy1 = min(by1, ey1)
                    if ix0 < ix1 and iy0 < iy1:
                        inter_area = (ix1 - ix0) * (iy1 - iy0)
                        new_area = max((bx1 - bx0) * (by1 - by0), 1e-6)
                        if inter_area / new_area > _OVERLAP_COVERAGE_THRESHOLD:
                            already_covered = True
                            break
                if already_covered:
                    continue

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

    # Collect all matching region IDs (existing + new) using fuzzy match
    all_ids = []
    for r in doc.regions:
        if r.action == RegionAction.CANCEL:
            continue
        r_norm = _normalize(r.text.strip())
        if not r_norm:
            continue
        if needle_norm in r_norm or r_norm in needle_norm or _fuzzy_ratio(needle_norm, r_norm) >= _FUZZY_THRESHOLD:
            all_ids.append(r.id)

    save_doc(doc)

    return {
        "created": len(new_regions),
        "new_regions": [r.model_dump(mode="json") for r in new_regions],
        "all_ids": all_ids,
    }
