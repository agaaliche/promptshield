"""Character-offset ↔ TextBlock mapping and spatial helpers.

Maps character ranges in the full page text to bounding boxes, handles
gap-splitting, and provides offset computation strategies (clustered
and legacy).

Performance note (M3): ``_char_offset_to_bbox`` and
``_char_offsets_to_line_bboxes`` use binary search (bisect) on the
sorted block offsets for O(log B) lookup instead of O(B) linear scan.
"""

from __future__ import annotations

import bisect
import logging
from typing import Optional

from core.config import config
from core.detection.detection_config import BLOCK_ABSOLUTE_MAX_GAP_PX, BLOCK_MIN_GAP_LINE_RATIO
from models.schemas import BBox, PageData, TextBlock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Spatial thresholds for gap-splitting
# ---------------------------------------------------------------------------

_ABSOLUTE_MAX_GAP_PX: float = BLOCK_ABSOLUTE_MAX_GAP_PX
_MIN_GAP_LINE_RATIO: float = BLOCK_MIN_GAP_LINE_RATIO
_MAX_GAP_LINE_RATIO: float = 1.25
_GAP_OUTLIER_FACTOR: float = 3.0
_MAX_WORD_GAP_WS: int = 3


def _effective_gap_threshold(line_height: float) -> float:
    """Compute the spatial gap threshold in PDF pts.

    Scales linearly with ``detection_fuzziness`` (0 → 1) between
    ``_MIN_GAP_LINE_RATIO`` and ``_MAX_GAP_LINE_RATIO`` of *line_height*,
    clamped to ``_ABSOLUTE_MAX_GAP_PX``.
    """
    f = config.detection_fuzziness
    ratio = _MIN_GAP_LINE_RATIO + (_MAX_GAP_LINE_RATIO - _MIN_GAP_LINE_RATIO) * f
    return min(line_height * ratio, _ABSOLUTE_MAX_GAP_PX)


def _clamp_bbox(bbox: BBox, page_w: float, page_h: float) -> BBox:
    """Clamp bounding box coordinates to fit within page dimensions."""
    return BBox(
        x0=max(0.0, min(bbox.x0, page_w)),
        y0=max(0.0, min(bbox.y0, page_h)),
        x1=max(0.0, min(bbox.x1, page_w)),
        y1=max(0.0, min(bbox.y1, page_h)),
    )


def _blocks_overlapping_bbox(
    bbox: BBox,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> list[tuple[int, int, TextBlock]]:
    """Return block-offset triples whose TextBlock spatially overlaps *bbox*."""
    result: list[tuple[int, int, TextBlock]] = []
    for bstart, bend, block in block_offsets:
        bb = block.bbox
        if bb.x0 < bbox.x1 and bb.x1 > bbox.x0 and bb.y0 < bbox.y1 and bb.y1 > bbox.y0:
            result.append((bstart, bend, block))
    return result


def _split_blocks_at_gaps(
    triples: list[tuple[int, int, TextBlock]],
    full_text: str,
) -> list[list[tuple[int, int, TextBlock]]]:
    """Split a sequence of block-offset triples at large gaps.

    A split occurs when consecutive blocks (sorted left-to-right) have
    a spatial gap that BOTH exceeds the font-relative threshold AND is
    a clear outlier (≥ 3× the smallest same-line gap in the group).
    """
    if len(triples) <= 1:
        return [triples] if triples else []

    blocks = [t[2] for t in triples]
    max_h = max(b.bbox.y1 - b.bbox.y0 for b in blocks)
    y_centres = [(b.bbox.y0 + b.bbox.y1) / 2 for b in blocks]
    single_line = (max(y_centres) - min(y_centres)) <= max_h * 0.5

    if single_line:
        sorted_t = sorted(triples, key=lambda t: t[2].bbox.x0)
    else:
        sorted_t = sorted(
            triples,
            key=lambda t: ((t[2].bbox.y0 + t[2].bbox.y1) / 2, t[2].bbox.x0),
        )

    # First pass: collect same-line gap measurements
    same_line_gaps: list[float] = []
    for i in range(1, len(sorted_t)):
        prev_blk = sorted_t[i - 1][2]
        curr_blk = sorted_t[i][2]
        prev_h = prev_blk.bbox.y1 - prev_blk.bbox.y0
        curr_h = curr_blk.bbox.y1 - curr_blk.bbox.y0
        line_h = max(prev_h, curr_h)
        tolerance = line_h * 0.5
        prev_yc = (prev_blk.bbox.y0 + prev_blk.bbox.y1) / 2
        curr_yc = (curr_blk.bbox.y0 + curr_blk.bbox.y1) / 2
        same_line = abs(curr_yc - prev_yc) < tolerance
        if same_line:
            gap = curr_blk.bbox.x0 - prev_blk.bbox.x1
            if gap > 0:
                same_line_gaps.append(gap)

    min_gap = min(same_line_gaps) if same_line_gaps else 0.0

    # Second pass: split at genuine gap outliers
    groups: list[list[tuple[int, int, TextBlock]]] = [[sorted_t[0]]]

    for i in range(1, len(sorted_t)):
        _, prev_ce, prev_blk = sorted_t[i - 1]
        curr_cs, _, curr_blk = sorted_t[i]

        prev_h = prev_blk.bbox.y1 - prev_blk.bbox.y0
        curr_h = curr_blk.bbox.y1 - curr_blk.bbox.y0
        line_h = max(prev_h, curr_h)
        tolerance = line_h * 0.5
        prev_yc = (prev_blk.bbox.y0 + prev_blk.bbox.y1) / 2
        curr_yc = (curr_blk.bbox.y0 + curr_blk.bbox.y1) / 2
        same_line = abs(curr_yc - prev_yc) < tolerance

        gap_px = (curr_blk.bbox.x0 - prev_blk.bbox.x1) if same_line else 0.0
        gap_threshold = _effective_gap_threshold(line_h)

        between = full_text[prev_ce:curr_cs] if prev_ce <= curr_cs else ""
        ws_count = sum(1 for ch in between if ch in " \t\n\r")

        absolute_exceeded = gap_px > gap_threshold
        if len(same_line_gaps) >= 2 and min_gap > 0:
            is_outlier = gap_px >= min_gap * _GAP_OUTLIER_FACTOR
        else:
            is_outlier = True

        if (absolute_exceeded and is_outlier) or ws_count > _MAX_WORD_GAP_WS:
            groups.append([sorted_t[i]])
        else:
            groups[-1].append(sorted_t[i])

    return groups


def _bbox_from_block_triples(
    triples: list[tuple[int, int, TextBlock]],
) -> BBox:
    """Compute a merged bounding box from block-offset triples."""
    return BBox(
        x0=min(t[2].bbox.x0 for t in triples),
        y0=min(t[2].bbox.y0 for t in triples),
        x1=max(t[2].bbox.x1 for t in triples),
        y1=max(t[2].bbox.y1 for t in triples),
    )


# ---------------------------------------------------------------------------
# Block-offset computation strategies
# ---------------------------------------------------------------------------


def _compute_block_offsets_legacy(
    text_blocks: list[TextBlock],
) -> list[tuple[int, int, TextBlock]]:
    """Legacy offset computation using simple ``(y0, x0)`` sort."""
    sorted_blocks = sorted(
        text_blocks, key=lambda b: (b.bbox.y0, b.bbox.x0)
    )
    offsets: list[tuple[int, int, TextBlock]] = []
    pos = 0
    prev_y: float | None = None
    line_height = 0.0

    for block in sorted_blocks:
        if prev_y is not None:
            gap = block.bbox.y0 - prev_y
            if line_height > 0 and gap > line_height * 0.6:
                pos += 1  # newline separator
            else:
                pos += 1  # word separator
        bstart = pos
        pos += len(block.text)
        offsets.append((bstart, pos, block))
        line_height = max(line_height, block.bbox.y1 - block.bbox.y0)
        prev_y = block.bbox.y0
    return offsets


def _compute_block_offsets_clustered(
    text_blocks: list[TextBlock],
) -> list[tuple[int, int, TextBlock]]:
    """Offset computation using line-clustering (matches the improved
    ``_build_full_text`` used for newly ingested documents).
    """
    from core.ingestion.loader import _cluster_into_lines

    lines = _cluster_into_lines(text_blocks)
    offsets: list[tuple[int, int, TextBlock]] = []
    pos = 0
    prev_y: float | None = None
    line_height = 0.0

    for line_blocks in lines:
        line_top = min(b.bbox.y0 for b in line_blocks)
        lh = max(b.bbox.y1 for b in line_blocks) - line_top

        for i, block in enumerate(line_blocks):
            if prev_y is not None or i > 0:
                if i == 0:
                    gap = line_top - prev_y if prev_y is not None else 0
                    if line_height > 0 and gap > line_height * 0.6:
                        pos += 1
                    else:
                        pos += 1
                else:
                    pos += 1
            bstart = pos
            pos += len(block.text)
            offsets.append((bstart, pos, block))

        prev_y = line_top
        line_height = lh
    return offsets


def _verify_offsets(
    offsets: list[tuple[int, int, TextBlock]],
    full_text: str,
    sample_count: int = 20,
) -> bool:
    """Verify that the first *sample_count* block offsets align with
    the given *full_text*.
    """
    for start, end, block in offsets[:sample_count]:
        if start < 0 or end > len(full_text):
            return False
        if full_text[start:end] != block.text:
            return False
    return True


def _compute_block_offsets(
    text_blocks: list[TextBlock],
    full_text: str,
) -> list[tuple[int, int, TextBlock]]:
    """Build a deterministic char-offset → TextBlock mapping.

    Tries the current line-clustering algorithm first.  Falls back to
    legacy computation if offsets don't align.

    Returns a list of ``(char_start, char_end, TextBlock)`` tuples.
    """
    if not text_blocks or not full_text:
        return []

    offsets = _compute_block_offsets_clustered(text_blocks)
    if _verify_offsets(offsets, full_text):
        logger.debug("Block offsets: clustered strategy succeeded (%d blocks)", len(offsets))
        return offsets

    offsets = _compute_block_offsets_legacy(text_blocks)
    if _verify_offsets(offsets, full_text):
        logger.debug("Block offsets: legacy strategy succeeded (%d blocks)", len(offsets))
        return offsets

    if offsets:
        first_start, _, first_block = offsets[0]
        idx = full_text.find(first_block.text)
        if idx >= 0 and idx != first_start:
            shift = first_start - idx
            offsets = [(s - shift, e - shift, blk) for s, e, blk in offsets]
            if _verify_offsets(offsets, full_text):
                logger.debug("Block offsets: shift-aligned strategy succeeded (%d blocks)", len(offsets))
                return offsets

    logger.debug("Block offsets: all strategies failed, returning legacy fallback")
    return _compute_block_offsets_legacy(text_blocks)


def _char_offset_to_bbox(
    char_start: int,
    char_end: int,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> Optional[BBox]:
    """Map character offsets in the full page text to a bounding box.

    Uses binary search (bisect) on block end positions for O(log B) lookup.
    """
    if not block_offsets:
        return None

    # Build end-position list for bisect (lazy, but fast for repeated calls
    # on the same block_offsets since Python caches list comprehensions).
    ends = [bo[1] for bo in block_offsets]

    overlapping: list[TextBlock] = []
    # Find first block whose end > char_start
    lo = bisect.bisect_right(ends, char_start)
    # lo may overshoot by 1 if char_start falls inside a block whose end == char_start
    if lo > 0 and block_offsets[lo - 1][1] > char_start:
        lo -= 1
    for i in range(max(0, lo - 1), len(block_offsets)):
        bstart, bend, block = block_offsets[i]
        if bstart >= char_end:
            break
        if bend > char_start:
            overlapping.append(block)

    if not overlapping:
        closest = min(
            block_offsets,
            key=lambda x: min(abs(x[0] - char_start), abs(x[1] - char_end)),
        )
        overlapping = [closest[2]]

    x0 = min(b.bbox.x0 for b in overlapping)
    y0 = min(b.bbox.y0 for b in overlapping)
    x1 = max(b.bbox.x1 for b in overlapping)
    y1 = max(b.bbox.y1 for b in overlapping)

    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _char_offsets_to_line_bboxes(
    char_start: int,
    char_end: int,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> list[BBox]:
    """Map character offsets to one bounding box **per visual line**.

    Uses binary search for O(log B) initial lookup.
    """
    if not block_offsets:
        return []

    ends = [bo[1] for bo in block_offsets]

    overlapping: list[TextBlock] = []
    lo = bisect.bisect_right(ends, char_start)
    if lo > 0 and block_offsets[lo - 1][1] > char_start:
        lo -= 1
    for i in range(max(0, lo - 1), len(block_offsets)):
        bstart, bend, block = block_offsets[i]
        if bstart >= char_end:
            break
        if bend > char_start:
            overlapping.append(block)

    if not overlapping:
        closest = min(
            block_offsets,
            key=lambda x: min(abs(x[0] - char_start), abs(x[1] - char_end)),
        )
        overlapping = [closest[2]]

    from core.ingestion.loader import _cluster_into_lines

    lines = _cluster_into_lines(overlapping)

    if len(lines) > 1:
        all_blocks = [b for line in lines for b in line]
        max_h = max(b.bbox.y1 - b.bbox.y0 for b in all_blocks)
        y_centres = [(b.bbox.y0 + b.bbox.y1) / 2 for b in all_blocks]
        y_spread = max(y_centres) - min(y_centres)
        if y_spread <= max_h:
            lines = [sorted(all_blocks, key=lambda b: b.bbox.x0)]

    bboxes: list[BBox] = []
    for line_blocks in lines:
        x0 = min(b.bbox.x0 for b in line_blocks)
        y0 = min(b.bbox.y0 for b in line_blocks)
        x1 = max(b.bbox.x1 for b in line_blocks)
        y1 = max(b.bbox.y1 for b in line_blocks)
        bboxes.append(BBox(x0=x0, y0=y0, x1=x1, y1=y1))

    return bboxes
