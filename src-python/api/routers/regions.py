"""PII region CRUD, batch operations, highlight-all, and reanalysis."""

from __future__ import annotations

import logging
from typing import Optional

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
from api.deps import get_doc, save_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["regions"])


# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}/debug-detections")
async def debug_detections(doc_id: str, page_number: Optional[int] = None):
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


# ---------------------------------------------------------------------------
# Single-region mutations
# ---------------------------------------------------------------------------

@router.put("/documents/{doc_id}/regions/{region_id}/action")
async def set_region_action(doc_id: str, region_id: str, req: RegionActionRequest):
    """Set the action for a specific PII region."""
    doc = get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.action = req.action
            save_doc(doc)
            return {"status": "ok", "region_id": region_id, "action": req.action.value}
    raise HTTPException(404, f"Region '{region_id}' not found")


@router.delete("/documents/{doc_id}/regions/{region_id}")
async def delete_region(doc_id: str, region_id: str):
    """Delete a PII region entirely from the document."""
    doc = get_doc(doc_id)
    original_len = len(doc.regions)
    doc.regions = [r for r in doc.regions if r.id != region_id]
    if len(doc.regions) == original_len:
        raise HTTPException(404, f"Region '{region_id}' not found")
    save_doc(doc)
    return {"status": "ok", "region_id": region_id}


@router.put("/documents/{doc_id}/regions/{region_id}/bbox")
async def update_region_bbox(doc_id: str, region_id: str, bbox: BBox):
    """Update the bounding box of a PII region (move / resize)."""
    doc = get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.bbox = bbox
            save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


class UpdateLabelRequest(_PydanticBaseModel):
    pii_type: PIIType


@router.put("/documents/{doc_id}/regions/{region_id}/label")
async def update_region_label(doc_id: str, region_id: str, req: UpdateLabelRequest):
    """Update the PII type label of a region."""
    doc = get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.pii_type = req.pii_type
            save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


class UpdateTextRequest(_PydanticBaseModel):
    text: str


@router.put("/documents/{doc_id}/regions/{region_id}/text")
async def update_region_text(doc_id: str, region_id: str, req: UpdateTextRequest):
    """Update the detected text content of a region."""
    doc = get_doc(doc_id)
    for region in doc.regions:
        if region.id == region_id:
            region.text = req.text
            save_doc(doc)
            return {"status": "ok", "region_id": region_id}
    raise HTTPException(404, f"Region '{region_id}' not found")


@router.post("/documents/{doc_id}/regions/{region_id}/reanalyze")
async def reanalyze_region(doc_id: str, region_id: str):
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
    result = reanalyze_bbox(page_data, region.bbox, llm_engine=engine)

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
        "confidence": region.confidence,
        "source": region.source if isinstance(region.source, str) else region.source.value,
    }


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

@router.put("/documents/{doc_id}/regions/batch-action")
async def batch_region_action(doc_id: str, req: BatchActionRequest):
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
async def batch_delete_regions(doc_id: str, req: BatchActionRequest):
    """Delete multiple regions at once."""
    doc = get_doc(doc_id)
    ids_to_delete = set(req.region_ids)
    original_len = len(doc.regions)
    doc.regions = [r for r in doc.regions if r.id not in ids_to_delete]
    deleted = original_len - len(doc.regions)
    save_doc(doc)
    return {"status": "ok", "deleted": deleted}


@router.post("/documents/{doc_id}/regions/add")
async def add_manual_region(doc_id: str, region: PIIRegion):
    """Add a manually selected PII region."""
    doc = get_doc(doc_id)
    region.source = "MANUAL"
    doc.regions.append(region)
    save_doc(doc)
    return {"status": "ok", "region_id": region.id}


# ---------------------------------------------------------------------------
# Highlight-all
# ---------------------------------------------------------------------------

class HighlightAllRequest(_PydanticBaseModel):
    region_id: str


@router.post("/documents/{doc_id}/regions/highlight-all")
async def highlight_all(doc_id: str, req: HighlightAllRequest):
    """Find all occurrences of a region's text across every page and create
    new MANUAL regions for any that don't already have one."""
    import traceback
    try:
        return _highlight_all_impl(doc_id, req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"highlight-all error: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, detail=str(e))


# ---------------------------------------------------------------------------
# Highlight-all helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize for fuzzy matching: lowercase, collapse whitespace, strip accents."""
    import unicodedata, re
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fuzzy_ratio(a: str, b: str) -> float:
    """Quick similarity ratio between two strings (0..1)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


_FUZZY_THRESHOLD = 0.75  # 75% similarity


def _highlight_all_impl(doc_id: str, req: HighlightAllRequest):
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
        if needle_len >= 2:
            window = needle_len
            for tol in (0, 1, 2):
                wlen = window + tol
                if wlen > len(full_norm):
                    continue
                for si in range(len(full_norm) - wlen + 1):
                    chunk = full_norm[si : si + wlen]
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
                        if _fuzzy_ratio(needle_norm, chunk) >= _FUZZY_THRESHOLD:
                            orig_start = norm_idx_to_orig(si)
                            orig_end = norm_idx_to_orig(si + wlen) if si + wlen < len(full_norm) else len(full_text)
                            if any(abs(orig_start - ms) < max(needle_len // 2, 2) for ms, _ in matches):
                                continue
                            matches.append((orig_start, orig_end))

        for idx, match_end in matches:
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
                    if inter_area / new_area > 0.4:
                        already_covered = True
                        break
            if already_covered:
                continue

            matched_text = full_text[idx:match_end]
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
