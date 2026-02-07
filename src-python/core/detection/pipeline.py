"""PII detection pipeline — merges results from regex, NER, and LLM layers."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from core.config import config
from core.detection.regex_detector import RegexMatch, detect_regex
from core.detection.ner_detector import NERMatch, detect_ner, is_ner_available
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
    ner_matches: list[NERMatch] = []
    if config.ner_enabled:
        if config.ner_backend != "spacy" and is_bert_ner_available():
            bert_results = detect_bert_ner(text)
            # BERTNERMatch is structurally identical to NERMatch
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                f"Page {page_data.page_number}: BERT NER ({config.ner_backend}) "
                f"found {len(ner_matches)} matches"
            )
        elif is_ner_available():
            ner_matches = detect_ner(text)
            logger.info(
                f"Page {page_data.page_number}: spaCy NER found {len(ner_matches)} matches"
            )

    # Layer 3: LLM (slowest — runs last)
    llm_matches: list[LLMMatch] = []
    if config.llm_detection_enabled and llm_engine is not None:
        llm_matches = detect_llm(text, llm_engine)
        logger.info(
            f"Page {page_data.page_number}: LLM found {len(llm_matches)} matches"
        )

    # Merge all layers
    regions = _merge_detections(regex_matches, ner_matches, llm_matches, page_data)
    logger.info(
        f"Page {page_data.page_number}: {len(regions)} merged PII regions "
        f"(regex={len(regex_matches)}, ner={len(ner_matches)}, llm={len(llm_matches)})"
    )

    return regions
