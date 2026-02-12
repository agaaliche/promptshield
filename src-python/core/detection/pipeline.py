"""PII detection pipeline — merges results from regex, NER, and LLM layers."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from core.config import config
from core.detection.regex_detector import RegexMatch, detect_regex
from core.detection.ner_detector import (
    NERMatch,
    detect_ner,
    is_ner_available,
    detect_names_heuristic,
    _is_english_text,
    _is_french_text,
    _is_italian_text,
    detect_ner_french,
    is_french_ner_available,
    detect_ner_italian,
    is_italian_ner_available,
)
from core.detection.gliner_detector import GLiNERMatch, detect_gliner, is_gliner_available
from core.detection.bert_detector import (
    NERMatch as BERTNERMatch,
    detect_bert_ner,
    is_bert_ner_available,
)
from core.detection.language import resolve_auto_model, SUPPORTED_LANGUAGES
from core.detection.llm_detector import LLMMatch, detect_llm
from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)

logger = logging.getLogger(__name__)


def _bbox_overlap_area(a: BBox, b: BBox) -> float:
    """Return the area of intersection between two bounding boxes."""
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _bbox_area(b: BBox) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _resolve_bbox_overlaps(regions: list[PIIRegion]) -> list[PIIRegion]:
    """
    Ensure no two highlight rectangles overlap on the same page.

    Strategy:
    1. Sort regions by area descending (process larger boxes first).
    2. For each pair with overlapping bboxes, shrink or clip the
       lower-confidence region so it no longer overlaps.
    3. If clipping would reduce a region to near-zero area, drop it.
    """
    if len(regions) <= 1:
        return regions

    # Work with a mutable copy; sort by confidence desc so we keep the
    # strongest regions intact and clip weaker ones around them.
    result = sorted(regions, key=lambda r: -r.confidence)
    final: list[PIIRegion] = []

    for region in result:
        bbox = BBox(
            x0=region.bbox.x0,
            y0=region.bbox.y0,
            x1=region.bbox.x1,
            y1=region.bbox.y1,
        )

        for keeper in final:
            if _bbox_overlap_area(bbox, keeper.bbox) <= 0:
                continue

            # The two boxes overlap — clip `bbox` away from `keeper.bbox`.
            # Choose the axis where the overlap is smallest to preserve
            # as much of the region as possible.
            overlap_x = min(bbox.x1, keeper.bbox.x1) - max(bbox.x0, keeper.bbox.x0)
            overlap_y = min(bbox.y1, keeper.bbox.y1) - max(bbox.y0, keeper.bbox.y0)

            # Determine which side of the keeper the region mostly lives on
            cx = (bbox.x0 + bbox.x1) / 2
            cy = (bbox.y0 + bbox.y1) / 2
            kcx = (keeper.bbox.x0 + keeper.bbox.x1) / 2
            kcy = (keeper.bbox.y0 + keeper.bbox.y1) / 2

            if overlap_y <= overlap_x:
                # Clip vertically
                if cy < kcy:
                    # Region is above the keeper — shrink bottom
                    bbox = BBox(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=keeper.bbox.y0)
                else:
                    # Region is below the keeper — shrink top
                    bbox = BBox(x0=bbox.x0, y0=keeper.bbox.y1, x1=bbox.x1, y1=bbox.y1)
            else:
                # Clip horizontally
                if cx < kcx:
                    # Region is left of keeper — shrink right
                    bbox = BBox(x0=bbox.x0, y0=bbox.y0, x1=keeper.bbox.x0, y1=bbox.y1)
                else:
                    # Region is right of keeper — shrink left
                    bbox = BBox(x0=keeper.bbox.x1, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1)

        # Drop regions that became too small (< 2pt in either dimension)
        if bbox.width < 2 or bbox.height < 2:
            continue

        final.append(region.model_copy(update={"bbox": bbox}))

    return final


# ---------------------------------------------------------------------------
# Region shape constraints
# ---------------------------------------------------------------------------

# Hard-capped absolute maximum gap — beyond this, words are in separate
# columns / form fields regardless of fuzziness.  20 PDF pts ≈ 0.28 in ≈ 7 mm.
_ABSOLUTE_MAX_GAP_PX = 20.0
_MIN_GAP_LINE_RATIO = 0.50    # Gap ratio at fuzziness=0  (strict)
_MAX_GAP_LINE_RATIO = 1.25    # Gap ratio at fuzziness=1  (permissive)
_GAP_OUTLIER_FACTOR = 3.0     # Gap must be ≥ 3× the smallest same-line gap to split
_MAX_WORD_GAP_WS = 3          # Max whitespace chars between consecutive words
_MAX_WORDS_PER_REGION = 4     # Words beyond this trigger split + re-detection


def _effective_gap_threshold(line_height: float) -> float:
    """Compute the spatial gap threshold in PDF pts.

    Scales linearly with ``detection_fuzziness`` (0 → 1) between
    ``_MIN_GAP_LINE_RATIO`` and ``_MAX_GAP_LINE_RATIO`` of *line_height*,
    clamped to ``_ABSOLUTE_MAX_GAP_PX``.

    Typical results (at default fuzziness=0.5):
      10 pt font →  ~8.75 pt threshold (0.875 × 10)
      12 pt font → ~10.5 pt threshold  (0.875 × 12)
      14 pt font → ~12.25 pt threshold (0.875 × 14)
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
    a clear outlier (≥ 3× the smallest same-line gap in the group) —
    this prevents splitting at uniform word spacing caused by bbox
    edge variance from font glyph sidebearings.  A split also occurs
    when more than ``_MAX_WORD_GAP_WS`` (3) whitespace characters
    separate blocks in the page's full text.
    """
    if len(triples) <= 1:
        return [triples] if triples else []

    # Sort blocks into proper reading order.  Raw (y0, x0) sorting fails
    # when same-line blocks have slightly different y0 due to font metrics
    # or OCR variance (e.g. "Canada" y0=53.22 vs "9169270" y0=53.35 puts
    # Canada before 9169270 even though 9169270 is 60pt to the left).
    # Fix: if all blocks fit on one visual line, sort by x0 only.
    # Otherwise, use y-centre (stable) then x0.
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

    # ── First pass: collect all same-line gap measurements ───────
    same_line_gaps: list[float] = []
    for i in range(1, len(sorted_t)):
        prev_blk = sorted_t[i - 1][2]
        curr_blk = sorted_t[i][2]

        prev_h = prev_blk.bbox.y1 - prev_blk.bbox.y0
        curr_h = curr_blk.bbox.y1 - curr_blk.bbox.y0
        line_h = max(prev_h, curr_h)
        tolerance = line_h * 0.5
        # Use y-centre for same-line (consistent with _cluster_into_lines)
        prev_yc = (prev_blk.bbox.y0 + prev_blk.bbox.y1) / 2
        curr_yc = (curr_blk.bbox.y0 + curr_blk.bbox.y1) / 2
        same_line = abs(curr_yc - prev_yc) < tolerance

        if same_line:
            gap = curr_blk.bbox.x0 - prev_blk.bbox.x1
            if gap > 0:
                same_line_gaps.append(gap)

    min_gap = min(same_line_gaps) if same_line_gaps else 0.0

    # ── Second pass: split at genuine gap outliers ───────────────
    groups: list[list[tuple[int, int, TextBlock]]] = [[sorted_t[0]]]

    for i in range(1, len(sorted_t)):
        _, prev_ce, prev_blk = sorted_t[i - 1]
        curr_cs, _, curr_blk = sorted_t[i]

        prev_h = prev_blk.bbox.y1 - prev_blk.bbox.y0
        curr_h = curr_blk.bbox.y1 - curr_blk.bbox.y0
        line_h = max(prev_h, curr_h)
        tolerance = line_h * 0.5
        # Use y-centre for same-line (consistent with _cluster_into_lines)
        prev_yc = (prev_blk.bbox.y0 + prev_blk.bbox.y1) / 2
        curr_yc = (curr_blk.bbox.y0 + curr_blk.bbox.y1) / 2
        same_line = abs(curr_yc - prev_yc) < tolerance

        # Spatial gap (only meaningful on the same visual line)
        gap_px = (curr_blk.bbox.x0 - prev_blk.bbox.x1) if same_line else 0.0
        gap_threshold = _effective_gap_threshold(line_h)

        # Text gap (whitespace chars between blocks in full_text)
        between = full_text[prev_ce:curr_cs] if prev_ce <= curr_cs else ""
        ws_count = sum(1 for ch in between if ch in " \t\n\r")

        # Spatial split requires BOTH absolute threshold AND relative
        # outlier status — prevents splitting at uniform word spacing
        # caused by font glyph sidebearing differences.
        absolute_exceeded = gap_px > gap_threshold
        if len(same_line_gaps) >= 2 and min_gap > 0:
            is_outlier = gap_px >= min_gap * _GAP_OUTLIER_FACTOR
        else:
            is_outlier = True  # ≤1 gap → fall back to absolute check only

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


def _redetect_pii(text: str) -> tuple[PIIType, float, DetectionSource] | None:
    """Run lightweight regex + NER re-detection on *text*.

    Returns ``(pii_type, confidence, source)`` for the highest-confidence
    match, or ``None`` if nothing exceeds the confidence threshold.
    Used to validate/reclassify chunks produced by word-limit splitting.
    """
    best: tuple[PIIType, float, DetectionSource] | None = None

    # Regex (fast, reliable for structured PII)
    if config.regex_enabled:
        for m in detect_regex(text):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.REGEX)

    # spaCy NER (fast on short text)
    if config.ner_enabled and is_ner_available():
        for m in detect_ner(text):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.NER)

    # Heuristic name detection (good even on 1-2 word fragments)
    if config.ner_enabled:
        for m in detect_names_heuristic(text):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.NER)

    if best is not None and best[1] >= config.confidence_threshold:
        return best
    return None


def _enforce_region_shapes(
    regions: list[PIIRegion],
    page_data: PageData,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> list[PIIRegion]:
    """Post-process regions to enforce shape-quality constraints.

    Rules (applied in order):
    1. **Bounds clamping** — bbox cannot exceed page dimensions.
    2. **Word-gap splitting** — consecutive words distanced by more than
       6 PDF pts or 3 whitespace chars become separate regions.
    3. **Word-count limit** — regions covering more than 4 words are
       split into ≤ 4-word chunks; each chunk is re-validated via
       regex + NER.  Chunks that fail re-detection are kept at 50 %
       confidence (dropped if below the global threshold) to prevent
       data leaks from unconfirmed highlights.
    """
    if not block_offsets:
        return regions

    page_w, page_h = page_data.width, page_data.height
    result: list[PIIRegion] = []

    for region in regions:
        # ── 1. Clamp to page bounds ──────────────────────────────────
        clamped = _clamp_bbox(region.bbox, page_w, page_h)
        if clamped.x1 - clamped.x0 < 1.0 or clamped.y1 - clamped.y0 < 1.0:
            continue  # degenerate after clamping
        region = region.model_copy(update={"bbox": clamped})

        # ── 2. Find overlapping TextBlocks ───────────────────────────
        triples = _blocks_overlapping_bbox(region.bbox, block_offsets)
        if not triples:
            # Manual region or geometry mismatch — keep as-is
            result.append(region)
            continue

        # ── 3. Split at word gaps ────────────────────────────────────
        gap_groups = _split_blocks_at_gaps(triples, page_data.full_text)

        # Fast path: single group, within word limit → keep original
        if len(gap_groups) == 1 and len(gap_groups[0]) <= _MAX_WORDS_PER_REGION:
            result.append(region)
            continue

        # ── 4. Process each gap-group (may need word-limit splitting) ─
        for group in gap_groups:
            if len(group) <= _MAX_WORDS_PER_REGION:
                # Small group from gap split — create sub-region, keep
                # original PII type (no re-detection needed).
                sub_bbox = _clamp_bbox(
                    _bbox_from_block_triples(group), page_w, page_h,
                )
                if sub_bbox.x1 - sub_bbox.x0 < 1.0 or sub_bbox.y1 - sub_bbox.y0 < 1.0:
                    continue
                sub_text = " ".join(t[2].text for t in group)
                cs = min(t[0] for t in group)
                ce = max(t[1] for t in group)
                result.append(PIIRegion(
                    id=uuid.uuid4().hex[:16],
                    page_number=region.page_number,
                    bbox=sub_bbox,
                    text=sub_text,
                    pii_type=region.pii_type,
                    confidence=region.confidence,
                    source=region.source,
                    char_start=cs,
                    char_end=ce,
                    action=region.action,
                ))
            else:
                # > 4 words — split into chunks and re-detect each
                sorted_group = sorted(
                    group, key=lambda t: (t[2].bbox.y0, t[2].bbox.x0),
                )
                for ci in range(0, len(sorted_group), _MAX_WORDS_PER_REGION):
                    chunk = sorted_group[ci:ci + _MAX_WORDS_PER_REGION]
                    sub_bbox = _clamp_bbox(
                        _bbox_from_block_triples(chunk), page_w, page_h,
                    )
                    if sub_bbox.x1 - sub_bbox.x0 < 1.0 or sub_bbox.y1 - sub_bbox.y0 < 1.0:
                        continue
                    sub_text = " ".join(t[2].text for t in chunk)
                    cs = min(t[0] for t in chunk)
                    ce = max(t[1] for t in chunk)

                    # Re-detect PII type on this chunk
                    detection = _redetect_pii(sub_text)
                    if detection is not None:
                        pii_type, confidence, source = detection
                    else:
                        # No re-detection hit — keep original type at
                        # reduced confidence to flag uncertainty.
                        pii_type = region.pii_type
                        confidence = region.confidence * 0.5
                        source = region.source
                        if confidence < config.confidence_threshold:
                            continue  # drop unconfirmed chunk

                    result.append(PIIRegion(
                        id=uuid.uuid4().hex[:16],
                        page_number=region.page_number,
                        bbox=sub_bbox,
                        text=sub_text,
                        pii_type=pii_type,
                        confidence=confidence,
                        source=source,
                        char_start=cs,
                        char_end=ce,
                        action=region.action,
                    ))

    logger.debug(
        f"Shape enforcement: {len(regions)} regions → {len(result)} "
        f"(page {page_data.page_number})"
    )
    return result


def _compute_block_offsets_legacy(
    text_blocks: list[TextBlock],
) -> list[tuple[int, int, TextBlock]]:
    """Legacy offset computation using simple ``(y0, x0)`` sort.

    Matches the original ``_build_full_text`` that was used for
    documents ingested before the line-clustering improvement.
    """
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
                pos += 1
            else:
                pos += 1
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
                        pos += 1  # "\n"
                    else:
                        pos += 1  # " "
                else:
                    pos += 1  # " "
            bstart = pos
            pos += len(block.text)
            offsets.append((bstart, pos, block))

        prev_y = line_top
        line_height = lh
    return offsets


def _verify_offsets(
    offsets: list[tuple[int, int, TextBlock]],
    full_text: str,
    sample_count: int = 5,
) -> bool:
    """Verify that the first *sample_count* block offsets align with
    the given *full_text*.  Returns ``True`` if all checked blocks
    match, ``False`` otherwise.
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
    """
    Build a deterministic char-offset → TextBlock mapping that matches
    how ``_build_full_text`` constructs ``full_text``.

    Tries the current line-clustering algorithm first.  If the offsets
    don't align with the stored *full_text* (e.g. because the document
    was ingested with the older simple-sort algorithm), falls back to
    the legacy computation.

    Returns a list of ``(char_start, char_end, TextBlock)`` tuples.
    """
    if not text_blocks or not full_text:
        return []

    # Try current (line-clustered) algorithm first
    offsets = _compute_block_offsets_clustered(text_blocks)
    if _verify_offsets(offsets, full_text):
        return offsets

    # Fallback: legacy (y0, x0) sort
    offsets = _compute_block_offsets_legacy(text_blocks)
    if _verify_offsets(offsets, full_text):
        return offsets

    # Last resort: shift offsets to align with full_text if possible
    if offsets:
        first_start, _, first_block = offsets[0]
        idx = full_text.find(first_block.text)
        if idx >= 0 and idx != first_start:
            shift = first_start - idx
            offsets = [(s - shift, e - shift, blk) for s, e, blk in offsets]
            if _verify_offsets(offsets, full_text):
                return offsets

    # Give up — return legacy offsets un-shifted (better than nothing)
    return _compute_block_offsets_legacy(text_blocks)


def _char_offset_to_bbox(
    char_start: int,
    char_end: int,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> Optional[BBox]:
    """
    Map character offsets in the full page text to a bounding box
    using a pre-computed block offset map.
    """
    if not block_offsets:
        return None

    # Find all blocks that overlap with [char_start, char_end)
    overlapping: list[TextBlock] = []
    for bstart, bend, block in block_offsets:
        if bstart < char_end and bend > char_start:
            overlapping.append(block)

    if not overlapping:
        # Fallback: find the closest block by distance to char range
        closest = min(
            block_offsets,
            key=lambda x: min(abs(x[0] - char_start), abs(x[1] - char_end)),
        )
        overlapping = [closest[2]]

    # Merge bounding boxes of all overlapping blocks
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

    If a matched span covers blocks on multiple lines, this returns one
    tight bbox per line instead of a single tall rectangle.  Regions that
    span more than one line are almost always false positives from the
    union of unrelated blocks; splitting keeps highlights line-height.
    """
    if not block_offsets:
        return []

    # Gather overlapping blocks
    overlapping: list[TextBlock] = []
    for bstart, bend, block in block_offsets:
        if bstart < char_end and bend > char_start:
            overlapping.append(block)

    if not overlapping:
        closest = min(
            block_offsets,
            key=lambda x: min(abs(x[0] - char_start), abs(x[1] - char_end)),
        )
        overlapping = [closest[2]]

    # Cluster overlapping blocks into visual lines (same logic as ingestion)
    from core.ingestion.loader import _cluster_into_lines

    lines = _cluster_into_lines(overlapping)

    # If clustering produced multiple "lines" but all blocks are really on
    # the same visual line (small vertical spread relative to line height),
    # merge them back.  _cluster_into_lines can over-split when individual
    # blocks have slightly different y-centres due to OCR / font metrics.
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


def _merge_detections(
    regex_matches: list[RegexMatch],
    ner_matches: list[NERMatch],
    llm_matches: list[LLMMatch],
    page_data: PageData,
    gliner_matches: list[GLiNERMatch] | None = None,
) -> list[PIIRegion]:
    """
    Merge detection results from all layers into unified PIIRegion list.

    Strategy:
    1. Convert all matches to a common format with char offsets.
    2. **Cross-layer confidence boost** — when 2+ independent layers flag
       the same span, the winner gets a confidence bump.
    3. Sort by start position.
    4. Merge overlapping regions — keep higher priority source.
       Priority for structured data: REGEX > NER > LLM
       Priority for contextual data: LLM > NER > REGEX
    """
    # Structured PII types (regex is most reliable for these)
    structured_types = {
        PIIType.SSN, PIIType.EMAIL, PIIType.PHONE,
        PIIType.CREDIT_CARD, PIIType.IBAN, PIIType.IP_ADDRESS,
        PIIType.DATE,
    }
    # Semi-structured: regex patterns are precise but NER/GLiNER also strong
    # — give them equal priority so confidence decides overlaps.
    semi_structured_types = {PIIType.ORG, PIIType.ADDRESS}

    # Convert all to common intermediate format
    candidates: list[dict] = []

    for m in regex_matches:
        if m.pii_type in structured_types:
            prio = 3
        elif m.pii_type in semi_structured_types:
            prio = 2  # same as NER/GLiNER — confidence breaks ties
        else:
            prio = 1
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.REGEX,
            "priority": prio,
        })

    for m in ner_matches:
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.NER,
            "priority": 2,
        })

    for m in (gliner_matches or []):
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.GLINER,
            "priority": 2,
        })

    for m in llm_matches:
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.LLM,
            "priority": 1 if m.pii_type in structured_types else 3,
        })

    # ------------------------------------------------------------------
    # Cross-layer confidence boost
    # When multiple layers independently detect the same span, boost the
    # highest-priority candidate's confidence.
    #
    # Optimised: sort by start position, then scan forward only while
    # candidates can still overlap (start < current end).  This cuts
    # typical O(n²) down to O(n·k) where k ≤ overlap-cluster size.
    # ------------------------------------------------------------------
    _BOOST_2_LAYERS = 0.10
    _BOOST_3_LAYERS = 0.15

    # Pre-sort a copy by start for the scan (original order restored later)
    idx_sorted = sorted(range(len(candidates)), key=lambda k: candidates[k]["start"])

    for ii in range(len(idx_sorted)):
        i = idx_sorted[ii]
        c = candidates[i]
        overlapping_sources: set[str] = {c["source"]}
        c_end = c["end"]

        # Scan forward — candidates are sorted by start, so once
        # other["start"] >= c_end no further overlap is possible.
        for jj in range(ii + 1, len(idx_sorted)):
            j = idx_sorted[jj]
            other = candidates[j]
            if other["start"] >= c_end:
                break
            # Check for significant overlap (≥50% of either span)
            overlap_start = max(c["start"], other["start"])
            overlap_end = min(c_end, other["end"])
            if overlap_end <= overlap_start:
                continue
            overlap_len = overlap_end - overlap_start
            c_len = c_end - c["start"]
            o_len = other["end"] - other["start"]
            if c_len > 0 and o_len > 0:
                ratio = overlap_len / min(c_len, o_len)
                if ratio >= 0.5:
                    overlapping_sources.add(other["source"])

        n_layers = len(overlapping_sources)
        if n_layers >= 3:
            c["confidence"] = min(1.0, c["confidence"] + _BOOST_3_LAYERS)
        elif n_layers == 2:
            c["confidence"] = min(1.0, c["confidence"] + _BOOST_2_LAYERS)

    # Sort by start position, then by priority descending
    candidates.sort(key=lambda x: (x["start"], -x["priority"]))

    # Merge overlapping regions
    merged: list[dict] = []
    for cand in candidates:
        if not merged:
            merged.append(cand)
            continue

        last = merged[-1]
        # Check overlap
        if cand["start"] < last["end"]:
            # Overlapping — keep the one with higher priority (or higher confidence)
            if cand["priority"] > last["priority"]:
                merged[-1] = cand
            elif cand["priority"] == last["priority"] and cand["confidence"] > last["confidence"]:
                merged[-1] = cand
            # Extend end if new candidate goes further
            if cand["end"] > last["end"]:
                merged[-1]["end"] = cand["end"]
                merged[-1]["text"] = page_data.full_text[merged[-1]["start"]:cand["end"]]
        else:
            merged.append(cand)

    # Pre-compute deterministic block-offset map once for this page
    block_offsets = _compute_block_offsets(
        page_data.text_blocks, page_data.full_text,
    )

    # Convert to PIIRegion with bounding boxes — one region per visual line
    regions: list[PIIRegion] = []
    for item in merged:
        # Filter by confidence threshold
        if item["confidence"] < config.confidence_threshold:
            continue

        line_bboxes = _char_offsets_to_line_bboxes(
            item["start"], item["end"],
            block_offsets,
        )
        if not line_bboxes:
            # Fallback to single bbox via legacy function
            bbox = _char_offset_to_bbox(item["start"], item["end"], block_offsets)
            if bbox is None:
                continue
            line_bboxes = [bbox]

        for bbox in line_bboxes:
            regions.append(PIIRegion(
                id=uuid.uuid4().hex[:12],
                page_number=page_data.page_number,
                bbox=bbox,
                text=item["text"],
                pii_type=item["pii_type"],
                confidence=item["confidence"],
                source=item["source"],
                char_start=item["start"],
                char_end=item["end"],
            ))

    # Enforce region shape constraints (bounds, word gaps, word limit)
    regions = _enforce_region_shapes(regions, page_data, block_offsets)

    # Resolve any remaining bounding-box overlaps
    regions = _resolve_bbox_overlaps(regions)

    return regions


# ---------------------------------------------------------------------------
# Cross-page propagation
# ---------------------------------------------------------------------------

def propagate_regions_across_pages(
    regions: list[PIIRegion],
    pages: list[PageData],
) -> list[PIIRegion]:
    """Ensure every detected PII text is flagged on *every* page where it
    appears, not just the page where it was first detected.

    For each unique PII text in *regions*, search all pages for additional
    occurrences that don't already have a corresponding region, and create
    new regions with properly-computed bounding boxes.

    The new regions inherit ``pii_type``, ``confidence``, ``source``, and
    ``action`` from the original detection (the one with highest confidence
    if the same text was found by multiple detectors).

    Returns the full region list (originals + propagated).
    """
    if not regions or not pages:
        return regions

    # Build a lookup: page_number → PageData
    page_map: dict[int, PageData] = {p.page_number: p for p in pages}

    # Collect unique PII texts and their best (highest-confidence) region
    # as the "template" for propagated copies.
    text_to_template: dict[str, PIIRegion] = {}
    for r in regions:
        key = r.text.strip()
        if not key or len(key) < 2:
            continue
        existing = text_to_template.get(key)
        if existing is None or r.confidence > existing.confidence:
            text_to_template[key] = r

    if not text_to_template:
        return regions

    # Build a set of (page_number, char_start, char_end) already covered
    covered: set[tuple[int, int, int]] = set()
    for r in regions:
        covered.add((r.page_number, r.char_start, r.char_end))

    propagated: list[PIIRegion] = []

    for pii_text, template in text_to_template.items():
        for page_data in pages:
            # Search for all occurrences of pii_text in the page's full_text
            full_text = page_data.full_text
            if not full_text:
                continue

            start = 0
            while True:
                idx = full_text.find(pii_text, start)
                if idx == -1:
                    break
                char_start = idx
                char_end = idx + len(pii_text)
                start = char_end  # advance past this occurrence

                # Skip if already covered by an existing region
                # (check for any significant overlap, not exact match)
                already = False
                for pg, cs, ce in covered:
                    if pg != page_data.page_number:
                        continue
                    # Overlap check: the spans share at least 50%
                    ov_start = max(char_start, cs)
                    ov_end = min(char_end, ce)
                    if ov_end > ov_start:
                        ov_len = ov_end - ov_start
                        if ov_len >= 0.5 * len(pii_text):
                            already = True
                            break
                if already:
                    continue

                # Compute bbox(es) for this occurrence — one per visual line
                block_offsets = _compute_block_offsets(
                    page_data.text_blocks, full_text,
                )
                line_bboxes = _char_offsets_to_line_bboxes(
                    char_start, char_end, block_offsets,
                )
                if not line_bboxes:
                    bbox = _char_offset_to_bbox(char_start, char_end, block_offsets)
                    if bbox is None:
                        continue
                    line_bboxes = [bbox]

                for bbox in line_bboxes:
                    # Clamp to page bounds — propagated regions bypass
                    # _enforce_region_shapes so must be clamped here.
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
                covered.add((page_data.page_number, char_start, char_end))

    if propagated:
        logger.info(
            f"Propagated {len(propagated)} additional regions across "
            f"{len(pages)} pages from {len(text_to_template)} unique PII texts"
        )

    all_regions = regions + propagated

    # Final overlap resolution on the combined set, grouped by page
    result: list[PIIRegion] = []
    pages_with_regions: set[int] = {r.page_number for r in all_regions}
    for pn in sorted(pages_with_regions):
        page_regions = [r for r in all_regions if r.page_number == pn]
        result.extend(_resolve_bbox_overlaps(page_regions))

    # Safety: clamp every region to its page bounds (belt-and-suspenders)
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


def detect_pii_on_page(
    page_data: PageData,
    llm_engine=None,
) -> list[PIIRegion]:
    """
    Run the full hybrid PII detection pipeline on a single page.

    Args:
        page_data: Extracted page with text blocks.
        llm_engine: Optional LLMEngine for Layer 3 detection.

    Returns:
        List of PIIRegion instances ready for UI display.
    """
    text = page_data.full_text
    stripped = text.strip()
    if not stripped:
        return []

    # Skip pages with very little content (cover pages, separator pages,
    # boilerplate headers).  These contain no meaningful PII and sending
    # them through NER / GLiNER / LLM wastes time and can trigger LLM
    # assertion failures on degenerate short prompts.
    _MIN_PAGE_CHARS = 30
    if len(stripped) < _MIN_PAGE_CHARS:
        logger.info(
            "Page %d: only %d chars — skipping detection",
            page_data.page_number, len(stripped),
        )
        return []

    page_t0 = time.perf_counter()
    timings: dict[str, float] = {}

    # Layer 1: Regex (always fast)
    regex_matches: list[RegexMatch] = []
    if config.regex_enabled:
        t0 = time.perf_counter()
        # Build effective allowed types: merge regex-tab types with any
        # NER-tab types that regex patterns also produce (e.g. ORG from
        # numbered-company patterns, ADDRESS from structured patterns).
        # This avoids silently dropping regex matches whose PIIType lives
        # under the NER toggle in the UI.
        effective_regex_types = None
        if config.regex_types is not None:
            effective_regex_types = list(set(config.regex_types))
            if config.ner_types is not None:
                # Add NER-tab types that are enabled — regex patterns that
                # emit these types should still fire.
                effective_regex_types = list(
                    set(effective_regex_types) | set(config.ner_types)
                )
            else:
                # NER types unfiltered — allow all NER-tab types through regex
                effective_regex_types = None
        regex_matches = detect_regex(text, allowed_types=effective_regex_types)
        timings["regex"] = (time.perf_counter() - t0) * 1000
        logger.info(
            f"Page {page_data.page_number}: Regex found {len(regex_matches)} matches"
        )

    # Layer 2: NER (spaCy, HuggingFace BERT, or auto-select)
    # Always supplements with heuristic name detection for coverage.
    ner_matches: list[NERMatch] = []
    if config.ner_enabled:
        t0 = time.perf_counter()

        if config.ner_backend == "auto" and is_bert_ner_available():
            # Auto mode: detect language and pick the best model
            auto_model, detected_lang = resolve_auto_model(text)
            bert_results = detect_bert_ner(text, model_id=auto_model)
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                f"Page {page_data.page_number}: Auto NER — lang={detected_lang}, "
                f"model={auto_model}, found {len(ner_matches)} matches"
            )
        elif config.ner_backend not in ("spacy", "auto") and is_bert_ner_available():
            # Specific BERT model selected — use it directly
            bert_results = detect_bert_ner(text)
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                f"Page {page_data.page_number}: BERT NER ({config.ner_backend}) "
                f"found {len(ner_matches)} matches"
            )
        # Fall back to spaCy (when spaCy selected, or BERT unavailable)
        elif is_ner_available():
            ner_matches = detect_ner(text)
            logger.info(
                f"Page {page_data.page_number}: spaCy NER found {len(ner_matches)} matches"
            )
        timings["ner"] = (time.perf_counter() - t0) * 1000

        # Always run lightweight heuristic as a supplement —
        # catches names that NER models miss (especially small models).
        t0 = time.perf_counter()
        heuristic_matches = detect_names_heuristic(text)
        if heuristic_matches:
            # Only add heuristic matches that don't overlap with existing NER
            existing_spans = {(m.start, m.end) for m in ner_matches}
            for hm in heuristic_matches:
                overlaps = any(
                    hm.start < e_end and hm.end > e_start
                    for e_start, e_end in existing_spans
                )
                if not overlaps:
                    ner_matches.append(hm)
            logger.info(
                f"Page {page_data.page_number}: Heuristic added "
                f"{len(heuristic_matches)} name candidates"
            )
        timings["heuristic"] = (time.perf_counter() - t0) * 1000

        # French NER — runs alongside GLiNER to provide cross-layer boost
        if not _is_english_text(text) and _is_french_text(text) and is_french_ner_available():
            t0 = time.perf_counter()
            try:
                fr_matches = detect_ner_french(text)
                if fr_matches:
                    # Merge French NER results, skipping overlaps with existing
                    existing_spans = {(m.start, m.end) for m in ner_matches}
                    added = 0
                    for fm in fr_matches:
                        overlaps = any(
                            fm.start < e_end and fm.end > e_start
                            for e_start, e_end in existing_spans
                        )
                        if not overlaps:
                            ner_matches.append(fm)
                            existing_spans.add((fm.start, fm.end))
                            added += 1
                    logger.info(
                        f"Page {page_data.page_number}: French NER found "
                        f"{len(fr_matches)} matches, added {added} non-overlapping"
                    )
            except Exception as e:
                logger.error(f"French NER detection failed: {e}")
            timings["french_ner"] = (time.perf_counter() - t0) * 1000

        # Italian NER — runs alongside GLiNER to provide cross-layer boost
        if not _is_english_text(text) and _is_italian_text(text) and is_italian_ner_available():
            t0 = time.perf_counter()
            try:
                it_matches = detect_ner_italian(text)
                if it_matches:
                    # Merge Italian NER results, skipping overlaps with existing
                    existing_spans = {(m.start, m.end) for m in ner_matches}
                    added = 0
                    for im in it_matches:
                        overlaps = any(
                            im.start < e_end and im.end > e_start
                            for e_start, e_end in existing_spans
                        )
                        if not overlaps:
                            ner_matches.append(im)
                            existing_spans.add((im.start, im.end))
                            added += 1
                    logger.info(
                        f"Page {page_data.page_number}: Italian NER found "
                        f"{len(it_matches)} matches, added {added} non-overlapping"
                    )
            except Exception as e:
                logger.error(f"Italian NER detection failed: {e}")
            timings["italian_ner"] = (time.perf_counter() - t0) * 1000

    # Layer 2b: GLiNER (multilingual NER — runs on ALL languages)
    gliner_matches: list[GLiNERMatch] = []
    if config.ner_enabled and is_gliner_available():
        t0 = time.perf_counter()
        try:
            gliner_matches = detect_gliner(text)
            logger.info(
                f"Page {page_data.page_number}: GLiNER found {len(gliner_matches)} matches"
            )
        except Exception as e:
            logger.error(f"GLiNER detection failed: {e}")
        timings["gliner"] = (time.perf_counter() - t0) * 1000

    # Layer 3: LLM (slowest — runs last)
    llm_matches: list[LLMMatch] = []
    if config.llm_detection_enabled and llm_engine is not None:
        t0 = time.perf_counter()
        llm_matches = detect_llm(text, llm_engine)
        timings["llm"] = (time.perf_counter() - t0) * 1000
        logger.info(
            f"Page {page_data.page_number}: LLM found {len(llm_matches)} matches"
        )

    # ── Per-type filtering for NER / GLiNER ──
    if config.ner_types:
        _allowed_ner = set(config.ner_types)
        ner_matches = [m for m in ner_matches if (m.pii_type.value if hasattr(m.pii_type, 'value') else str(m.pii_type)) in _allowed_ner]
        gliner_matches = [m for m in gliner_matches if (m.pii_type.value if hasattr(m.pii_type, 'value') else str(m.pii_type)) in _allowed_ner]

    # ── Cross-layer filtering: if regex_types is set, NER/GLiNER/LLM must
    #    not produce types that belong to the regex tab but were disabled ──
    if config.regex_types is not None:
        _regex_tab_types = {"EMAIL", "PHONE", "SSN", "CREDIT_CARD", "IBAN", "DATE",
                            "IP_ADDRESS", "PASSPORT", "DRIVER_LICENSE", "ADDRESS"}
        _excluded_regex = _regex_tab_types - set(config.regex_types)
        if _excluded_regex:
            def _not_excluded(m):
                t = m.pii_type.value if hasattr(m.pii_type, 'value') else str(m.pii_type)
                return t not in _excluded_regex
            ner_matches = [m for m in ner_matches if _not_excluded(m)]
            gliner_matches = [m for m in gliner_matches if _not_excluded(m)]
            llm_matches = [m for m in llm_matches if _not_excluded(m)]

    # Merge all layers
    t0 = time.perf_counter()
    regions = _merge_detections(
        regex_matches, ner_matches, llm_matches, page_data,
        gliner_matches=gliner_matches,
    )
    timings["merge"] = (time.perf_counter() - t0) * 1000

    page_total = (time.perf_counter() - page_t0) * 1000
    timing_parts = " | ".join(f"{k}={v:.0f}ms" for k, v in timings.items())
    logger.info(
        f"Page {page_data.page_number}: {len(regions)} merged PII regions "
        f"({len(stripped)} chars) — {timing_parts} — total={page_total:.0f}ms"
    )

    return regions


def reanalyze_bbox(
    page_data: PageData,
    bbox: BBox,
    llm_engine=None,
) -> dict:
    """
    Analyze the text content under a bounding box and return the best
    PII classification.

    Returns dict with keys: text, pii_type, confidence, source.
    """
    # 1. Extract text blocks that overlap the given bbox
    overlapping_text_parts: list[str] = []
    for block in page_data.text_blocks:
        bb = block.bbox
        # Check spatial overlap
        if bb.x0 < bbox.x1 and bb.x1 > bbox.x0 and bb.y0 < bbox.y1 and bb.y1 > bbox.y0:
            overlapping_text_parts.append(block.text)

    text = " ".join(overlapping_text_parts).strip()
    if not text:
        return {"text": "", "pii_type": "CUSTOM", "confidence": 0.0, "source": "MANUAL"}

    # 2. Run detection layers on the extracted text
    regex_matches = detect_regex(text) if config.regex_enabled else []

    ner_matches: list[NERMatch] = []
    if config.ner_enabled:
        if config.ner_backend == "auto" and is_bert_ner_available():
            auto_model, _ = resolve_auto_model(text)
            bert_results = detect_bert_ner(text, model_id=auto_model)
            ner_matches = [NERMatch(*m) for m in bert_results]
        elif config.ner_backend not in ("spacy", "auto") and is_bert_ner_available():
            bert_results = detect_bert_ner(text)
            ner_matches = [NERMatch(*m) for m in bert_results]
        elif is_ner_available():
            ner_matches = detect_ner(text)

        # Supplement with heuristic
        heuristic_matches = detect_names_heuristic(text)
        existing_spans = {(m.start, m.end) for m in ner_matches}
        for hm in heuristic_matches:
            if not any(hm.start < ee and hm.end > es for es, ee in existing_spans):
                ner_matches.append(hm)

        # French NER supplement
        if not _is_english_text(text) and _is_french_text(text) and is_french_ner_available():
            try:
                fr_matches = detect_ner_french(text)
                existing_spans = {(m.start, m.end) for m in ner_matches}
                for fm in fr_matches:
                    if not any(fm.start < ee and fm.end > es for es, ee in existing_spans):
                        ner_matches.append(fm)
            except Exception:
                pass

        # Italian NER supplement
        if not _is_english_text(text) and _is_italian_text(text) and is_italian_ner_available():
            try:
                it_matches = detect_ner_italian(text)
                existing_spans = {(m.start, m.end) for m in ner_matches}
                for im in it_matches:
                    if not any(im.start < ee and im.end > es for es, ee in existing_spans):
                        ner_matches.append(im)
            except Exception:
                pass

    llm_matches: list[LLMMatch] = []
    if config.llm_detection_enabled and llm_engine is not None:
        llm_matches = detect_llm(text, llm_engine)

    # GLiNER (multilingual)
    gliner_matches: list[GLiNERMatch] = []
    if config.ner_enabled and is_gliner_available():
        try:
            gliner_matches = detect_gliner(text)
        except Exception:
            pass

    # 3. Pick the best match (highest confidence across all layers)
    best_type = "CUSTOM"
    best_confidence = 0.0
    best_source = "MANUAL"

    for m in regex_matches:
        if m.confidence > best_confidence:
            best_type = m.pii_type.value if hasattr(m.pii_type, "value") else str(m.pii_type)
            best_confidence = m.confidence
            best_source = "REGEX"

    for m in ner_matches:
        if m.confidence > best_confidence:
            best_type = m.pii_type.value if hasattr(m.pii_type, "value") else str(m.pii_type)
            best_confidence = m.confidence
            best_source = "NER"

    for m in gliner_matches:
        if m.confidence > best_confidence:
            best_type = m.pii_type.value if hasattr(m.pii_type, "value") else str(m.pii_type)
            best_confidence = m.confidence
            best_source = "GLINER"

    for m in llm_matches:
        if m.confidence > best_confidence:
            best_type = m.pii_type.value if hasattr(m.pii_type, "value") else str(m.pii_type)
            best_confidence = m.confidence
            best_source = "LLM"

    logger.info(
        f"Reanalyze bbox: text='{text[:50]}' -> {best_type} "
        f"({best_confidence:.0%}, {best_source})"
    )

    return {
        "text": text,
        "pii_type": best_type,
        "confidence": best_confidence,
        "source": best_source,
    }
