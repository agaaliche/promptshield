"""PII detection pipeline — merges results from regex, NER, and LLM layers."""

from __future__ import annotations

import logging
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
    detect_ner_french,
    is_french_ner_available,
)
from core.detection.gliner_detector import GLiNERMatch, detect_gliner, is_gliner_available
from core.detection.bert_detector import (
    NERMatch as BERTNERMatch,
    detect_bert_ner,
    is_bert_ner_available,
)
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


def _char_offset_to_bbox(
    char_start: int,
    char_end: int,
    text_blocks: list[TextBlock],
    full_text: str,
) -> Optional[BBox]:
    """
    Map character offsets in the full page text to a bounding box.

    Strategy: reconstruct character positions from text blocks and find
    which blocks overlap with the given character range.
    """
    if not text_blocks:
        return None

    # Build a map of char-offset → text block
    current_offset = 0
    block_offsets: list[tuple[int, int, TextBlock]] = []

    for block in text_blocks:
        # Find this block's text in the full text starting from current_offset
        idx = full_text.find(block.text, current_offset)
        if idx == -1:
            # Try from beginning (in case of text reordering)
            idx = full_text.find(block.text)
        if idx == -1:
            continue

        block_start = idx
        block_end = idx + len(block.text)
        block_offsets.append((block_start, block_end, block))
        current_offset = block_end

    # Find all blocks that overlap with [char_start, char_end)
    overlapping: list[TextBlock] = []
    for bstart, bend, block in block_offsets:
        if bstart < char_end and bend > char_start:
            overlapping.append(block)

    if not overlapping:
        # Fallback: find the closest block
        if block_offsets:
            closest = min(
                block_offsets,
                key=lambda x: abs(x[0] - char_start),
            )
            overlapping = [closest[2]]
        else:
            return None

    # Merge bounding boxes of all overlapping blocks
    x0 = min(b.bbox.x0 for b in overlapping)
    y0 = min(b.bbox.y0 for b in overlapping)
    x1 = max(b.bbox.x1 for b in overlapping)
    y1 = max(b.bbox.y1 for b in overlapping)

    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


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

    # Convert all to common intermediate format
    candidates: list[dict] = []

    for m in regex_matches:
        candidates.append({
            "start": m.start, "end": m.end, "text": m.text,
            "pii_type": m.pii_type, "confidence": m.confidence,
            "source": DetectionSource.REGEX,
            "priority": 3 if m.pii_type in structured_types else 1,
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
    # ------------------------------------------------------------------
    _BOOST_2_LAYERS = 0.10
    _BOOST_3_LAYERS = 0.15

    for i, c in enumerate(candidates):
        overlapping_sources: set[str] = {c["source"]}
        for j, other in enumerate(candidates):
            if i == j:
                continue
            # Check for significant overlap (≥50% of either span)
            overlap_start = max(c["start"], other["start"])
            overlap_end = min(c["end"], other["end"])
            if overlap_end <= overlap_start:
                continue
            overlap_len = overlap_end - overlap_start
            c_len = c["end"] - c["start"]
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

    # Convert to PIIRegion with bounding boxes
    regions: list[PIIRegion] = []
    for item in merged:
        # Filter by confidence threshold
        if item["confidence"] < config.confidence_threshold:
            continue

        bbox = _char_offset_to_bbox(
            item["start"], item["end"],
            page_data.text_blocks, page_data.full_text,
        )
        if bbox is None:
            continue

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

    # Resolve any remaining bounding-box overlaps
    regions = _resolve_bbox_overlaps(regions)

    return regions


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
    if not text.strip():
        return []

    # Layer 1: Regex (always fast)
    regex_matches: list[RegexMatch] = []
    if config.regex_enabled:
        regex_matches = detect_regex(text)
        logger.info(
            f"Page {page_data.page_number}: Regex found {len(regex_matches)} matches"
        )

    # Layer 2: NER (spaCy or HuggingFace BERT, depending on config)
    # Always supplements with heuristic name detection for coverage.
    ner_matches: list[NERMatch] = []
    if config.ner_enabled:
        # Try BERT first if configured — but only on English text
        # (BERT models are English-only; non-English text produces garbage)
        if config.ner_backend != "spacy" and is_bert_ner_available() and _is_english_text(text):
            bert_results = detect_bert_ner(text)
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                f"Page {page_data.page_number}: BERT NER ({config.ner_backend}) "
                f"found {len(ner_matches)} matches"
            )
        elif config.ner_backend != "spacy" and is_bert_ner_available() and not _is_english_text(text):
            logger.info(
                f"Page {page_data.page_number}: Skipping BERT NER — text is not English"
            )
        # Fall back to spaCy (even if config says BERT, if BERT unavailable)
        elif is_ner_available():
            ner_matches = detect_ner(text)
            logger.info(
                f"Page {page_data.page_number}: spaCy NER found {len(ner_matches)} matches"
            )

        # Always run lightweight heuristic as a supplement —
        # catches names that NER models miss (especially small models).
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

        # French NER — runs alongside GLiNER to provide cross-layer boost
        if not _is_english_text(text) and _is_french_text(text) and is_french_ner_available():
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

    # Layer 2b: GLiNER (multilingual NER — runs on ALL languages)
    gliner_matches: list[GLiNERMatch] = []
    if config.ner_enabled and is_gliner_available():
        try:
            gliner_matches = detect_gliner(text)
            logger.info(
                f"Page {page_data.page_number}: GLiNER found {len(gliner_matches)} matches"
            )
        except Exception as e:
            logger.error(f"GLiNER detection failed: {e}")

    # Layer 3: LLM (slowest — runs last)
    llm_matches: list[LLMMatch] = []
    if config.llm_detection_enabled and llm_engine is not None:
        llm_matches = detect_llm(text, llm_engine)
        logger.info(
            f"Page {page_data.page_number}: LLM found {len(llm_matches)} matches"
        )

    # Merge all layers
    regions = _merge_detections(
        regex_matches, ner_matches, llm_matches, page_data,
        gliner_matches=gliner_matches,
    )
    logger.info(
        f"Page {page_data.page_number}: {len(regions)} merged PII regions "
        f"(regex={len(regex_matches)}, ner={len(ner_matches)}, "
        f"gliner={len(gliner_matches)}, llm={len(llm_matches)})"
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
        if config.ner_backend != "spacy" and is_bert_ner_available() and _is_english_text(text):
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
