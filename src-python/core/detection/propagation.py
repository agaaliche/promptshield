"""Cross-page PII propagation.

Ensures every detected PII text is flagged on *every* page where it
appears, not just the page where it was first detected.

Performance optimisations (X1/X2):
- Block offsets are computed once per page and cached.
- The ``covered`` overlap check uses a per-page sorted interval list
  with binary search instead of a global linear scan.
"""

from __future__ import annotations

import bisect
import logging
import uuid
from collections import defaultdict

from core.detection.bbox_utils import _resolve_bbox_overlaps
from core.detection.block_offsets import (
    _clamp_bbox,
    _compute_block_offsets,
    _char_offset_to_bbox,
    _char_offsets_to_line_bboxes,
)
from core.detection.noise_filters import (
    _is_loc_pipeline_noise,
    _is_person_pipeline_noise,
    _STRUCTURED_MIN_DIGITS,
)
from models.schemas import (
    PIIRegion,
    PIIType,
    PageData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-page interval tracker — O(log n) overlap check via binary search
# ---------------------------------------------------------------------------

class _PageIntervals:
    """Maintain sorted, non-overlapping intervals per page for fast overlap checks."""

    __slots__ = ("_starts", "_ends")

    def __init__(self) -> None:
        self._starts: list[int] = []
        self._ends: list[int] = []

    def has_overlap(self, cs: int, ce: int, min_ratio: float = 0.5) -> bool:
        """Return True if an existing interval overlaps [cs, ce) by >= min_ratio.

        Uses binary search on sorted start positions — O(log n).
        """
        threshold = min_ratio * (ce - cs)
        # Find candidate intervals that could overlap [cs, ce).
        # An interval (s, e) overlaps [cs, ce) iff s < ce AND e > cs.
        # idx = first position where _starts[idx] >= ce  →  all intervals
        # with index < idx have start < ce (necessary condition for overlap).
        idx = bisect.bisect_left(self._starts, ce)
        # Walk backwards from idx to find intervals that also satisfy e > cs.
        for i in range(idx - 1, -1, -1):
            if self._ends[i] <= cs:
                # Intervals are sorted by start; all earlier intervals
                # have even smaller start values.  If this interval's end
                # doesn't reach cs, earlier ones won't either UNLESS they
                # are wider.  We must keep scanning because starts are
                # sorted but ends are not guaranteed to be monotone.
                # However, for the typical "no nesting" case we can
                # optimise: once we've gone past the start by more than
                # a reasonable margin, stop scanning.
                if self._starts[i] < cs - (ce - cs) * 2:
                    break
                continue
            ov_start = max(cs, self._starts[i])
            ov_end = min(ce, self._ends[i])
            if ov_end - ov_start >= threshold:
                return True
        return False

    def add(self, cs: int, ce: int) -> None:
        """Insert interval [cs, ce) maintaining sorted order by start."""
        idx = bisect.bisect_left(self._starts, cs)
        self._starts.insert(idx, cs)
        self._ends.insert(idx, ce)


def propagate_regions_across_pages(
    regions: list[PIIRegion],
    pages: list[PageData],
) -> list[PIIRegion]:
    """Ensure every detected PII text is flagged on *every* page.

    For each unique PII text in *regions*, search all pages for
    additional occurrences and create new regions with properly-computed
    bounding boxes.

    Returns the full region list (originals + propagated).
    """
    if not regions or not pages:
        return regions

    page_map: dict[int, PageData] = {p.page_number: p for p in pages}

    # Collect unique PII texts and their best template
    text_to_template: dict[str, PIIRegion] = {}
    for r in regions:
        key = r.text.strip()
        if not key or len(key) < 2:
            continue
        if r.pii_type == PIIType.ORG and (
            key.isdigit()
            or (key and key[0].isdigit())
            or len(key) <= 2
        ):
            continue
        if r.pii_type == PIIType.LOCATION and _is_loc_pipeline_noise(key):
            continue
        if r.pii_type == PIIType.PERSON and _is_person_pipeline_noise(key):
            continue
        _min_prop = _STRUCTURED_MIN_DIGITS.get(r.pii_type)
        if _min_prop is not None:
            digs = sum(c.isdigit() for c in key)
            if digs < _min_prop:
                continue
            if r.pii_type == PIIType.SSN and any(c in key for c in '$€£'):
                continue
        existing = text_to_template.get(key)
        if existing is None or r.confidence > existing.confidence:
            text_to_template[key] = r

    if not text_to_template:
        logger.debug("Propagation: no propagatable PII texts found")
        return regions

    # X2: Per-page interval index for O(log n) overlap check
    page_intervals: dict[int, _PageIntervals] = defaultdict(_PageIntervals)
    for r in regions:
        page_intervals[r.page_number].add(r.char_start, r.char_end)

    # X1: Cache block offsets per page (computed once, reused for all texts)
    block_offsets_cache: dict[int, list] = {}

    propagated: list[PIIRegion] = []

    for pii_text, template in text_to_template.items():
        for page_data in pages:
            full_text = page_data.full_text
            if not full_text:
                continue

            pn = page_data.page_number
            intervals = page_intervals[pn]

            start = 0
            while True:
                idx = full_text.find(pii_text, start)
                if idx == -1:
                    break
                char_start = idx
                char_end = idx + len(pii_text)
                start = char_end

                if intervals.has_overlap(char_start, char_end, 0.5):
                    continue

                # X1: Get cached block offsets for this page
                if pn not in block_offsets_cache:
                    block_offsets_cache[pn] = _compute_block_offsets(
                        page_data.text_blocks, full_text,
                    )
                block_offsets = block_offsets_cache[pn]

                line_bboxes = _char_offsets_to_line_bboxes(
                    char_start, char_end, block_offsets,
                )
                if not line_bboxes:
                    bbox = _char_offset_to_bbox(char_start, char_end, block_offsets)
                    if bbox is None:
                        continue
                    line_bboxes = [bbox]

                for bbox in line_bboxes:
                    clamped = _clamp_bbox(bbox, page_data.width, page_data.height)
                    if clamped.x1 - clamped.x0 < 1.0 or clamped.y1 - clamped.y0 < 1.0:
                        continue
                    new_region = PIIRegion(
                        id=uuid.uuid4().hex[:12],
                        page_number=page_data.page_number,
                        bbox=clamped,
                        text=pii_text,
                        pii_type=template.pii_type,
                        confidence=template.confidence,
                        source=template.source,
                        char_start=char_start,
                        char_end=char_end,
                        action=template.action,
                    )
                    propagated.append(new_region)
                intervals.add(char_start, char_end)

    if propagated:
        logger.info(
            "Propagated %d additional regions across %d pages from %d unique PII texts",
            len(propagated), len(pages), len(text_to_template),
        )

    all_regions = regions + propagated

    # Final overlap resolution per page
    result: list[PIIRegion] = []
    pages_with_regions: set[int] = {r.page_number for r in all_regions}
    for pn in sorted(pages_with_regions):
        page_regions = [r for r in all_regions if r.page_number == pn]
        result.extend(_resolve_bbox_overlaps(page_regions))

    # Clamp every region to its page bounds 
    clamped_result: list[PIIRegion] = []
    for r in result:
        pd = page_map.get(r.page_number)
        if pd is None:
            clamped_result.append(r)
            continue
        cb = _clamp_bbox(r.bbox, pd.width, pd.height)
        if cb.x1 - cb.x0 < 1.0 or cb.y1 - cb.y0 < 1.0:
            continue
        if cb != r.bbox:
            r = r.model_copy(update={"bbox": cb})
        clamped_result.append(r)

    return clamped_result
