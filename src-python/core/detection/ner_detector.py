"""spaCy NER-based PII detector — Layer 2 of the hybrid pipeline.

Detects named entities: PERSON, ORG, GPE, DATE, LOC, MONEY, etc.
Supports transformer models (en_core_web_trf) for highest accuracy,
with automatic fallback to lg → sm.  Long texts are processed in
overlapping chunks so NER quality stays high.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from models.schemas import PIIType

logger = logging.getLogger(__name__)


class NERMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# Map spaCy entity labels to our PII types
_SPACY_LABEL_MAP: dict[str, PIIType] = {
    "PERSON": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "GPE": PIIType.LOCATION,      # Countries, cities, states
    "LOC": PIIType.LOCATION,      # Non-GPE locations
    "DATE": PIIType.DATE,
    "NORP": PIIType.ORG,          # Nationalities, religious/political groups
    "FAC": PIIType.ADDRESS,       # Facilities / buildings
    "MONEY": PIIType.UNKNOWN,     # Financial amounts can be PII in context
}

# spaCy model (lazy-loaded)
_nlp = None
_active_model_name: str = ""

# Model cascade order depending on user preference
_MODEL_CASCADE: dict[str, list[str]] = {
    "trf": ["en_core_web_trf", "en_core_web_lg", "en_core_web_sm"],
    "lg":  ["en_core_web_lg", "en_core_web_sm"],
    "sm":  ["en_core_web_sm"],
}

# Chunking parameters (in characters)
_CHUNK_SIZE = 100_000          # Process in 100k-char chunks
_CHUNK_OVERLAP = 500           # 500-char overlap so entities at boundaries aren't lost


def _load_model():
    """Lazy-load the best available spaCy model based on config preference."""
    global _nlp, _active_model_name
    if _nlp is not None:
        return _nlp

    import spacy
    from core.config import config

    preference = getattr(config, "ner_model_preference", "trf")
    cascade = _MODEL_CASCADE.get(preference, _MODEL_CASCADE["trf"])

    for model_name in cascade:
        try:
            _nlp = spacy.load(model_name)
            _active_model_name = model_name
            logger.info(f"Loaded spaCy model '{model_name}'")
            return _nlp
        except OSError:
            logger.info(f"spaCy model '{model_name}' not installed — trying next")

    # Nothing installed — attempt to download en_core_web_sm as last resort
    logger.warning("No spaCy model found. Downloading en_core_web_sm…")
    try:
        spacy.cli.download("en_core_web_sm")
        _nlp = spacy.load("en_core_web_sm")
        _active_model_name = "en_core_web_sm"
        logger.info("Using fallback model 'en_core_web_sm'")
        return _nlp
    except Exception as e:
        logger.error(f"Failed to load any spaCy model: {e}")
        raise RuntimeError(
            "No spaCy NER model available. Install one with: "
            "python -m spacy download en_core_web_lg"
        ) from e


def _process_chunk(nlp, text: str, global_offset: int) -> list[NERMatch]:
    """Run NER on a single text chunk, adjusting offsets to the global text."""
    doc = nlp(text)
    matches: list[NERMatch] = []

    for ent in doc.ents:
        pii_type = _SPACY_LABEL_MAP.get(ent.label_)
        if pii_type is None:
            continue
        if len(ent.text.strip()) < 2:
            continue

        confidence = _estimate_confidence(ent, pii_type)
        matches.append(NERMatch(
            start=global_offset + ent.start_char,
            end=global_offset + ent.end_char,
            text=ent.text,
            pii_type=pii_type,
            confidence=confidence,
        ))

    return matches


def _deduplicate_matches(matches: list[NERMatch]) -> list[NERMatch]:
    """Remove duplicate matches from overlapping chunks.

    When two matches overlap (same span or one contains the other),
    keep the one with the higher confidence.
    """
    if not matches:
        return []

    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[NERMatch] = [matches[0]]

    for m in matches[1:]:
        prev = deduped[-1]
        # Same or overlapping span
        if m.start < prev.end:
            # Keep the one with higher confidence or longer span
            if m.confidence > prev.confidence or (m.end - m.start) > (prev.end - prev.start):
                deduped[-1] = m
        else:
            deduped.append(m)

    return deduped


def detect_ner(text: str) -> list[NERMatch]:
    """
    Run spaCy NER on text and return matches for PII-relevant entity types.

    Long texts are split into overlapping chunks so NER accuracy stays high.
    """
    nlp = _load_model()

    # Short texts — single pass (fast path)
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk(nlp, text[:1_000_000], global_offset=0)

    # Long texts — overlapping sliding-window
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk(nlp, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)

        # Advance by (chunk_size - overlap)
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate_matches(all_matches)


def _estimate_confidence(ent, pii_type: PIIType) -> float:
    """Estimate confidence for a spaCy entity based on heuristics."""
    base_confidence = {
        PIIType.PERSON: 0.85,
        PIIType.ORG: 0.75,
        PIIType.LOCATION: 0.75,
        PIIType.DATE: 0.70,
        PIIType.ADDRESS: 0.65,
        PIIType.UNKNOWN: 0.50,
    }
    conf = base_confidence.get(pii_type, 0.60)

    # Boost for longer entities (more likely correct)
    text_len = len(ent.text.strip())
    if text_len > 10:
        conf = min(conf + 0.05, 0.95)
    elif text_len < 3:
        conf = max(conf - 0.15, 0.30)

    # Boost when using the transformer model (higher accuracy)
    if _active_model_name.endswith("_trf"):
        conf = min(conf + 0.08, 0.98)
    elif _active_model_name.endswith("_lg"):
        conf = min(conf + 0.03, 0.95)

    return conf


def get_active_model_name() -> str:
    """Return the name of the currently loaded spaCy model."""
    return _active_model_name


def is_ner_available() -> bool:
    """Check if NER is available without raising."""
    try:
        _load_model()
        return True
    except Exception:
        return False
