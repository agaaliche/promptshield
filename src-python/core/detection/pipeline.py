"""PII detection pipeline — orchestrates regex, NER, GLiNER, BERT, and LLM layers.

This module is the main entry point for running PII detection on a page.
The heavy implementation is split across submodules:

- ``bbox_utils``     — bounding-box geometry helpers
- ``block_offsets``  — character-offset ↔ TextBlock mapping
- ``noise_filters``  — noise word sets and predicate functions
- ``region_shapes``  — shape constraint enforcement
- ``cross_line``     — cross-line ORG boundary scanning
- ``merge``          — multi-layer detection merging
- ``propagation``    — cross-page PII propagation
"""

from __future__ import annotations

import logging
import time
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
from core.detection.language import resolve_auto_model, detect_language, SUPPORTED_LANGUAGES
from core.detection.llm_detector import LLMMatch, detect_llm
from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)

# Sub-module imports for local use
from core.detection.cross_line import _detect_cross_line_orgs
from core.detection.merge import (                # noqa: F401
    _merge_detections,
    _split_bboxes_by_proximity,
)
from core.detection.propagation import propagate_regions_across_pages

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatibility re-exports
# ---------------------------------------------------------------------------
# External code (API routers, tests) imports many internal symbols from
# ``core.detection.pipeline``.  Re-export them here so existing imports
# continue to work without modification.

from core.detection.bbox_utils import (          # noqa: F401
    _bbox_overlap_area,
    _bbox_area,
    _resolve_bbox_overlaps,
)
from core.detection.block_offsets import (        # noqa: F401
    _ABSOLUTE_MAX_GAP_PX,
    _GAP_OUTLIER_FACTOR,
    _MAX_WORD_GAP_WS,
    _effective_gap_threshold,
    _clamp_bbox,
    _blocks_overlapping_bbox,
    _split_blocks_at_gaps,
    _bbox_from_block_triples,
    _compute_block_offsets,
    _char_offset_to_bbox,
    _char_offsets_to_line_bboxes,
)
from core.detection.noise_filters import (       # noqa: F401
    _is_org_pipeline_noise,
    _is_loc_pipeline_noise,
    _is_person_pipeline_noise,
    _is_address_number_only,
    _STRUCTURED_MIN_DIGITS,
    LEGAL_SUFFIX_RE,
    has_legal_suffix,
)
from core.detection.region_shapes import (       # noqa: F401
    _MAX_WORDS_DEFAULT,
    _max_words_for_type,
    _max_lines_for_type,
    _enforce_region_shapes,
    _redetect_pii,
)


# ---------------------------------------------------------------------------
# Main detection orchestrator
# ---------------------------------------------------------------------------


def detect_pii_on_page(
    page_data: PageData,
    llm_engine: Optional[object] = None,
) -> list[PIIRegion]:
    """Run the full hybrid PII detection pipeline on a single page.

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

    _MIN_PAGE_CHARS = 30
    if len(stripped) < _MIN_PAGE_CHARS:
        logger.info(
            "Page %d: only %d chars — skipping detection",
            page_data.page_number, len(stripped),
        )
        return []

    page_t0 = time.perf_counter()
    timings: dict[str, float] = {}

    # ── Resolve detection language once for this page ──
    if config.detection_language and config.detection_language != "auto":
        page_lang: str | None = config.detection_language
    else:
        page_lang = detect_language(text)

    # Layer 1: Regex
    regex_matches: list[RegexMatch] = []
    if config.regex_enabled:
        t0 = time.perf_counter()
        effective_regex_types = None
        if config.regex_types is not None:
            effective_regex_types = list(set(config.regex_types))
            if config.ner_types is not None:
                effective_regex_types = list(
                    set(effective_regex_types) | set(config.ner_types)
                )
            else:
                effective_regex_types = None
        regex_matches = detect_regex(text, allowed_types=effective_regex_types,
                                      detection_language=page_lang)
        timings["regex"] = (time.perf_counter() - t0) * 1000
        logger.info(
            "Page %d: Regex found %d matches",
            page_data.page_number, len(regex_matches),
        )

        # Cross-line ORG boundary scan
        t0 = time.perf_counter()
        cross_line_matches = _detect_cross_line_orgs(text)
        if cross_line_matches:
            existing_spans = [(m.start, m.end) for m in regex_matches]
            added = 0
            for cl in cross_line_matches:
                overlaps = any(
                    cl.start < e_end and cl.end > e_start
                    for e_start, e_end in existing_spans
                )
                if not overlaps:
                    regex_matches.append(cl)
                    existing_spans.append((cl.start, cl.end))
                    added += 1
            if added:
                logger.info(
                    "Page %d: Cross-line ORG scan added %d match(es)",
                    page_data.page_number, added,
                )
        timings["cross_line_org"] = (time.perf_counter() - t0) * 1000

    # Layer 2: NER (spaCy / BERT / auto)
    ner_matches: list[NERMatch] = []
    if config.ner_enabled:
        t0 = time.perf_counter()

        if config.ner_backend == "auto" and is_bert_ner_available():
            auto_model, detected_lang = resolve_auto_model(text)
            bert_results = detect_bert_ner(text, model_id=auto_model)
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                "Page %d: Auto NER — lang=%s, model=%s, found %d matches",
                page_data.page_number, detected_lang, auto_model, len(ner_matches),
            )
        elif config.ner_backend not in ("spacy", "auto") and is_bert_ner_available():
            bert_results = detect_bert_ner(text)
            ner_matches = [NERMatch(*m) for m in bert_results]
            logger.info(
                "Page %d: BERT NER (%s) found %d matches",
                page_data.page_number, config.ner_backend, len(ner_matches),
            )
        elif is_ner_available():
            ner_matches = detect_ner(text)
            logger.info(
                "Page %d: spaCy NER found %d matches",
                page_data.page_number, len(ner_matches),
            )
        timings["ner"] = (time.perf_counter() - t0) * 1000

        # Heuristic name supplement
        t0 = time.perf_counter()
        heuristic_matches = detect_names_heuristic(text)
        if heuristic_matches:
            existing_spans = {(m.start, m.end) for m in ner_matches}
            for hm in heuristic_matches:
                overlaps = any(
                    hm.start < e_end and hm.end > e_start
                    for e_start, e_end in existing_spans
                )
                if not overlaps:
                    ner_matches.append(hm)
            logger.info(
                "Page %d: Heuristic added %d name candidates",
                page_data.page_number, len(heuristic_matches),
            )
        timings["heuristic"] = (time.perf_counter() - t0) * 1000

        # French NER
        if not _is_english_text(text) and _is_french_text(text) and is_french_ner_available():
            t0 = time.perf_counter()
            try:
                fr_matches = detect_ner_french(text)
                if fr_matches:
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
                        "Page %d: French NER found %d matches, added %d non-overlapping",
                        page_data.page_number, len(fr_matches), added,
                    )
            except Exception as e:
                logger.error("French NER detection failed: %s", e)
            timings["french_ner"] = (time.perf_counter() - t0) * 1000

        # Italian NER
        if not _is_english_text(text) and _is_italian_text(text) and is_italian_ner_available():
            t0 = time.perf_counter()
            try:
                it_matches = detect_ner_italian(text)
                if it_matches:
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
                        "Page %d: Italian NER found %d matches, added %d non-overlapping",
                        page_data.page_number, len(it_matches), added,
                    )
            except Exception as e:
                logger.error("Italian NER detection failed: %s", e)
            timings["italian_ner"] = (time.perf_counter() - t0) * 1000

    # Layer 2b: GLiNER
    gliner_matches: list[GLiNERMatch] = []
    if config.ner_enabled and is_gliner_available():
        t0 = time.perf_counter()
        try:
            gliner_matches = detect_gliner(text)
            logger.info(
                "Page %d: GLiNER found %d matches",
                page_data.page_number, len(gliner_matches),
            )
        except Exception as e:
            logger.error("GLiNER detection failed: %s", e)
        timings["gliner"] = (time.perf_counter() - t0) * 1000

    # Layer 3: LLM
    llm_matches: list[LLMMatch] = []
    if config.llm_detection_enabled and llm_engine is not None:
        t0 = time.perf_counter()
        llm_matches = detect_llm(text, llm_engine)
        timings["llm"] = (time.perf_counter() - t0) * 1000
        logger.info(
            "Page %d: LLM found %d matches",
            page_data.page_number, len(llm_matches),
        )

    # ── Per-type filtering for NER / GLiNER ──
    if config.ner_types:
        _allowed_ner = set(config.ner_types)
        ner_matches = [m for m in ner_matches if (m.pii_type.value if hasattr(m.pii_type, 'value') else str(m.pii_type)) in _allowed_ner]
        gliner_matches = [m for m in gliner_matches if (m.pii_type.value if hasattr(m.pii_type, 'value') else str(m.pii_type)) in _allowed_ner]

    # ── Cross-layer type filtering ──
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
        "Page %d: %d merged PII regions (%d chars) — %s — total=%dms",
        page_data.page_number, len(regions), len(stripped),
        timing_parts, int(page_total),
    )

    return regions


def reanalyze_bbox(
    page_data: PageData,
    bbox: BBox,
    llm_engine: Optional[object] = None,
) -> dict:
    """Analyze the text content under a bounding box and return the best
    PII classification.

    Returns:
        Dict with keys: text, pii_type, confidence, source.
    """
    overlapping_text_parts: list[str] = []
    for block in page_data.text_blocks:
        bb = block.bbox
        if bb.x0 < bbox.x1 and bb.x1 > bbox.x0 and bb.y0 < bbox.y1 and bb.y1 > bbox.y0:
            overlapping_text_parts.append(block.text)

    text = " ".join(overlapping_text_parts).strip()
    if not text:
        return {"text": "", "pii_type": "CUSTOM", "confidence": 0.0, "source": "MANUAL"}

    _lang = config.detection_language if config.detection_language != "auto" else detect_language(text)
    regex_matches = detect_regex(text, detection_language=_lang) if config.regex_enabled else []

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

        heuristic_matches = detect_names_heuristic(text)
        existing_spans = {(m.start, m.end) for m in ner_matches}
        for hm in heuristic_matches:
            if not any(hm.start < ee and hm.end > es for es, ee in existing_spans):
                ner_matches.append(hm)

        if not _is_english_text(text) and _is_french_text(text) and is_french_ner_available():
            try:
                fr_matches = detect_ner_french(text)
                existing_spans = {(m.start, m.end) for m in ner_matches}
                for fm in fr_matches:
                    if not any(fm.start < ee and fm.end > es for es, ee in existing_spans):
                        ner_matches.append(fm)
            except Exception:
                pass

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

    gliner_matches: list[GLiNERMatch] = []
    if config.ner_enabled and is_gliner_available():
        try:
            gliner_matches = detect_gliner(text)
        except Exception:
            pass

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
        "Reanalyze bbox: text='%s' -> %s (%.0f%%, %s)",
        text[:50], best_type, best_confidence * 100, best_source,
    )

    return {
        "text": text,
        "pii_type": best_type,
        "confidence": best_confidence,
        "source": best_source,
    }
