"""Region shape constraints and enforcement.

Post-processes detected PII regions to enforce spatial/word-count
constraints, split regions at large gaps, and re-validate via
lightweight re-detection.
"""

from __future__ import annotations

import logging
import uuid

from core.config import config
from core.detection.regex_detector import detect_regex
from core.detection.ner_detector import (
    detect_ner,
    is_ner_available,
    detect_names_heuristic,
)
from core.detection.language import detect_language
from core.detection.block_offsets import (
    _clamp_bbox,
    _blocks_overlapping_bbox,
    _split_blocks_at_gaps,
    _bbox_from_block_triples,
)
from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-type limits
# ---------------------------------------------------------------------------

_MAX_LINES_BY_TYPE: dict[str, int] = {
    "ORG": 4,
    "ADDRESS": 4,
    "PERSON": 2,
}
_MAX_LINES_DEFAULT: int = 1

_MAX_WORDS_BY_TYPE: dict[str, int] = {
    "EMAIL":          1,
    "IP_ADDRESS":     1,
    "PASSPORT":       2,
    "SSN":            3,
    "DATE":           3,
    "DRIVER_LICENSE": 3,
    "PERSON":         4,
    "CREDIT_CARD":    4,
    "IBAN":           8,
    "PHONE":          8,
    "ORG":            8,
    "ADDRESS":        7,
}
_MAX_WORDS_DEFAULT: int = 4


def _max_words_for_type(pii_type: PIIType | str) -> int:
    """Return the word-count limit for a given PII type."""
    key = pii_type.value if hasattr(pii_type, "value") else str(pii_type)
    return _MAX_WORDS_BY_TYPE.get(key, _MAX_WORDS_DEFAULT)


def _max_lines_for_type(pii_type: PIIType | str) -> int:
    """Return the maximum visual lines for a given PII type."""
    key = pii_type.value if hasattr(pii_type, "value") else str(pii_type)
    return _MAX_LINES_BY_TYPE.get(key, _MAX_LINES_DEFAULT)


# ---------------------------------------------------------------------------
# Lightweight re-detection for split chunks
# ---------------------------------------------------------------------------


def _redetect_pii(text: str) -> tuple[PIIType, float, DetectionSource] | None:
    """Run lightweight regex + NER re-detection on *text*.

    Returns ``(pii_type, confidence, source)`` for the highest-confidence
    match, or ``None`` if nothing exceeds the confidence threshold.
    """
    best: tuple[PIIType, float, DetectionSource] | None = None

    if config.regex_enabled:
        _lang = config.detection_language if config.detection_language != "auto" else detect_language(text)
        for m in detect_regex(text, detection_language=_lang):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.REGEX)

    if config.ner_enabled and is_ner_available():
        for m in detect_ner(text):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.NER)

    if config.ner_enabled:
        for m in detect_names_heuristic(text):
            if best is None or m.confidence > best[1]:
                best = (m.pii_type, m.confidence, DetectionSource.NER)

    if best is not None and best[1] >= config.confidence_threshold:
        return best
    return None


# ---------------------------------------------------------------------------
# Main shape enforcement
# ---------------------------------------------------------------------------


def _enforce_region_shapes(
    regions: list[PIIRegion],
    page_data: PageData,
    block_offsets: list[tuple[int, int, TextBlock]],
) -> list[PIIRegion]:
    """Post-process regions to enforce shape-quality constraints.

    Rules (applied in order):
    1. Bounds clamping — bbox cannot exceed page dimensions.
    2. Word-gap splitting — consecutive words with large gaps split.
    3. Word-count limit — regions exceeding the per-type limit are
       split into chunks and re-validated.
    """
    if not block_offsets:
        return regions

    page_w, page_h = page_data.width, page_data.height
    result: list[PIIRegion] = []

    for region in regions:
        # 1. Clamp to page bounds
        clamped = _clamp_bbox(region.bbox, page_w, page_h)
        if clamped.x1 - clamped.x0 < 1.0 or clamped.y1 - clamped.y0 < 1.0:
            continue
        region = region.model_copy(update={"bbox": clamped})

        # 2. Find overlapping TextBlocks
        if region.char_start is not None and region.char_end is not None and region.char_start < region.char_end:
            triples = [
                (bs, be, blk)
                for bs, be, blk in block_offsets
                if be > region.char_start and bs < region.char_end
            ]
        else:
            triples = _blocks_overlapping_bbox(region.bbox, block_offsets)
        if not triples:
            result.append(region)
            continue

        # 3. Split at word gaps
        _wlimit = _max_words_for_type(region.pii_type)
        if region.pii_type == PIIType.ADDRESS:
            if len(triples) <= _wlimit:
                result.append(region)
                continue
            sorted_triples = sorted(
                triples, key=lambda t: (t[2].bbox.y0, t[2].bbox.x0),
            )
            for ci in range(0, len(sorted_triples), _wlimit):
                chunk = sorted_triples[ci:ci + _wlimit]
                sub_bbox = _clamp_bbox(
                    _bbox_from_block_triples(chunk), page_w, page_h,
                )
                if sub_bbox.x1 - sub_bbox.x0 < 1.0 or sub_bbox.y1 - sub_bbox.y0 < 1.0:
                    continue
                sub_text = " ".join(t[2].text for t in chunk)
                cs = min(t[0] for t in chunk)
                ce = max(t[1] for t in chunk)
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
                    linked_group=region.linked_group,
                ))
            continue

        gap_groups = _split_blocks_at_gaps(triples, page_data.full_text)

        if len(gap_groups) == 1 and len(gap_groups[0]) <= _wlimit:
            result.append(region)
            continue

        # 4. Process each gap-group
        for group in gap_groups:
            if len(group) <= _wlimit:
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
                    linked_group=region.linked_group,
                ))
            else:
                sorted_group = sorted(
                    group, key=lambda t: (t[2].bbox.y0, t[2].bbox.x0),
                )
                for ci in range(0, len(sorted_group), _wlimit):
                    chunk = sorted_group[ci:ci + _wlimit]
                    sub_bbox = _clamp_bbox(
                        _bbox_from_block_triples(chunk), page_w, page_h,
                    )
                    if sub_bbox.x1 - sub_bbox.x0 < 1.0 or sub_bbox.y1 - sub_bbox.y0 < 1.0:
                        continue
                    sub_text = " ".join(t[2].text for t in chunk)
                    cs = min(t[0] for t in chunk)
                    ce = max(t[1] for t in chunk)

                    detection = _redetect_pii(sub_text)
                    if detection is not None:
                        pii_type, confidence, source = detection
                    else:
                        pii_type = region.pii_type
                        confidence = region.confidence * 0.5
                        source = region.source
                        if confidence < config.confidence_threshold:
                            continue

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
                        linked_group=region.linked_group,
                    ))

    logger.debug(
        "Shape enforcement: %d regions → %d (page %d)",
        len(regions), len(result), page_data.page_number,
    )
    return result
