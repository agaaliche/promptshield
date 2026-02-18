"""Shared types and configuration for NER detection.

This module contains:
- NERMatch: Named tuple for NER detection results
- Label maps: Mapping spaCy entity labels to PIIType
- _LangNERConfig: Per-language configuration dataclass
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, NamedTuple

from models.schemas import PIIType


class NERMatch(NamedTuple):
    """A single NER match result."""
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# spaCy Entity Label Maps
# ---------------------------------------------------------------------------

# English spaCy label map
SPACY_EN_LABEL_MAP: dict[str, PIIType] = {
    "PERSON": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "GPE": PIIType.LOCATION,      # Countries, cities, states
    "LOC": PIIType.LOCATION,      # Non-GPE locations
    # DATE intentionally omitted — regex handles concrete dates much better;
    # NER dates are mostly noise ("Q4 2024", "the Year Ended ...", "Tuesday").
}

# French spaCy label map (uses PER not PERSON)
SPACY_FR_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    # MISC intentionally omitted — too noisy (adjectives, demonyms, etc.)
}

# Italian spaCy label map
SPACY_IT_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
}

# German spaCy label map
SPACY_DE_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
}

# Spanish spaCy label map
SPACY_ES_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
}

# Dutch spaCy label map (uses PERSON)
SPACY_NL_LABEL_MAP: dict[str, PIIType] = {
    "PERSON": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "GPE": PIIType.LOCATION,
    "LOC": PIIType.LOCATION,
}

# Portuguese spaCy label map
SPACY_PT_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
}

# Minimum entity text length per type (filter out noise)
MIN_ENTITY_LENGTH: dict[PIIType, int] = {
    PIIType.PERSON: 3,
    PIIType.ORG: 2,
    PIIType.LOCATION: 2,
    PIIType.DATE: 4,
    PIIType.ADDRESS: 3,
    PIIType.UNKNOWN: 3,
}


# ---------------------------------------------------------------------------
# Per-language NER Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LangNERConfig:
    """All per-language parameters that differ between language NER models."""

    label_map: dict[str, PIIType]
    article_prefixes: tuple[str, ...]
    strip_title_suffixes: bool  # True only for EN
    fp_person: Callable[[str], bool]
    fp_org: Callable[[str], bool]
    generic_stopwords_filter: bool  # extra generic stopwords check (EN only)
    active_model_name: Callable[[], str]
    # Confidence tuning
    base_confidence: dict[PIIType, float] = field(default_factory=dict)
    person_multiword_cap: float = 0.95
    org_3word_cap: float = 0.80
    person_single_penalty: float = 0.20
    org_single_floor: float = 0.25
    model_boost_tiers: tuple[tuple[str, float, float], ...] = ()
