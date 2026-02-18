"""Stop words and language detection utilities for NER.

This module provides:
- Lazy-loaded stop word sets for each supported language
- Language detection heuristics based on stop word frequency
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words — lazy-loaded to avoid ~200-400ms import cost at module level
# ---------------------------------------------------------------------------

_EN_STOP_WORDS: set[str] | None = None
_FR_STOP_WORDS: set[str] | None = None
_IT_STOP_WORDS: set[str] | None = None
_DE_STOP_WORDS: set[str] | None = None
_ES_STOP_WORDS: set[str] | None = None
_NL_STOP_WORDS: set[str] | None = None
_PT_STOP_WORDS: set[str] | None = None


def get_en_stop_words() -> set[str]:
    """Get English stop words (lazy-loaded)."""
    global _EN_STOP_WORDS
    if _EN_STOP_WORDS is None:
        from spacy.lang.en.stop_words import STOP_WORDS
        _EN_STOP_WORDS = STOP_WORDS
    return _EN_STOP_WORDS


def get_fr_stop_words() -> set[str]:
    """Get French stop words (lazy-loaded)."""
    global _FR_STOP_WORDS
    if _FR_STOP_WORDS is None:
        from spacy.lang.fr.stop_words import STOP_WORDS
        _FR_STOP_WORDS = STOP_WORDS
    return _FR_STOP_WORDS


def get_it_stop_words() -> set[str]:
    """Get Italian stop words (lazy-loaded)."""
    global _IT_STOP_WORDS
    if _IT_STOP_WORDS is None:
        from spacy.lang.it.stop_words import STOP_WORDS
        _IT_STOP_WORDS = STOP_WORDS
    return _IT_STOP_WORDS


def get_de_stop_words() -> set[str]:
    """Get German stop words (lazy-loaded)."""
    global _DE_STOP_WORDS
    if _DE_STOP_WORDS is None:
        from spacy.lang.de.stop_words import STOP_WORDS
        _DE_STOP_WORDS = STOP_WORDS
    return _DE_STOP_WORDS


def get_es_stop_words() -> set[str]:
    """Get Spanish stop words (lazy-loaded)."""
    global _ES_STOP_WORDS
    if _ES_STOP_WORDS is None:
        from spacy.lang.es.stop_words import STOP_WORDS
        _ES_STOP_WORDS = STOP_WORDS
    return _ES_STOP_WORDS


def get_nl_stop_words() -> set[str]:
    """Get Dutch stop words (lazy-loaded)."""
    global _NL_STOP_WORDS
    if _NL_STOP_WORDS is None:
        from spacy.lang.nl.stop_words import STOP_WORDS
        _NL_STOP_WORDS = STOP_WORDS
    return _NL_STOP_WORDS


def get_pt_stop_words() -> set[str]:
    """Get Portuguese stop words (lazy-loaded)."""
    global _PT_STOP_WORDS
    if _PT_STOP_WORDS is None:
        from spacy.lang.pt.stop_words import STOP_WORDS
        _PT_STOP_WORDS = STOP_WORDS
    return _PT_STOP_WORDS


# ---------------------------------------------------------------------------
# Lowercase stop word sets for language detection
# ---------------------------------------------------------------------------

_EN_STOP_LOWER: set[str] | None = None
_FR_STOP_LOWER: set[str] | None = None
_IT_STOP_LOWER: set[str] | None = None
_DE_STOP_LOWER: set[str] | None = None
_ES_STOP_LOWER: set[str] | None = None
_NL_STOP_LOWER: set[str] | None = None
_PT_STOP_LOWER: set[str] | None = None


def get_en_stop_lower() -> set[str]:
    """Get lowercase English stop words."""
    global _EN_STOP_LOWER
    if _EN_STOP_LOWER is None:
        _EN_STOP_LOWER = {w.lower() for w in get_en_stop_words()}
    return _EN_STOP_LOWER


def get_fr_stop_lower() -> set[str]:
    """Get lowercase French stop words."""
    global _FR_STOP_LOWER
    if _FR_STOP_LOWER is None:
        _FR_STOP_LOWER = {w.lower() for w in get_fr_stop_words()}
    return _FR_STOP_LOWER


def get_it_stop_lower() -> set[str]:
    """Get lowercase Italian stop words."""
    global _IT_STOP_LOWER
    if _IT_STOP_LOWER is None:
        _IT_STOP_LOWER = {w.lower() for w in get_it_stop_words()}
    return _IT_STOP_LOWER


def get_de_stop_lower() -> set[str]:
    """Get lowercase German stop words."""
    global _DE_STOP_LOWER
    if _DE_STOP_LOWER is None:
        _DE_STOP_LOWER = {w.lower() for w in get_de_stop_words()}
    return _DE_STOP_LOWER


def get_es_stop_lower() -> set[str]:
    """Get lowercase Spanish stop words."""
    global _ES_STOP_LOWER
    if _ES_STOP_LOWER is None:
        _ES_STOP_LOWER = {w.lower() for w in get_es_stop_words()}
    return _ES_STOP_LOWER


def get_nl_stop_lower() -> set[str]:
    """Get lowercase Dutch stop words."""
    global _NL_STOP_LOWER
    if _NL_STOP_LOWER is None:
        _NL_STOP_LOWER = {w.lower() for w in get_nl_stop_words()}
    return _NL_STOP_LOWER


def get_pt_stop_lower() -> set[str]:
    """Get lowercase Portuguese stop words."""
    global _PT_STOP_LOWER
    if _PT_STOP_LOWER is None:
        _PT_STOP_LOWER = {w.lower() for w in get_pt_stop_words()}
    return _PT_STOP_LOWER


# ---------------------------------------------------------------------------
# Language Detection Configuration
# ---------------------------------------------------------------------------

LANG_SAMPLE_SIZE = 2000  # characters to sample for language check
ENGLISH_STOPWORD_THRESHOLD = 0.15   # 15% — English text typically 25-40%
FRENCH_STOPWORD_THRESHOLD = 0.12    # 12% — French text typically 20-35%
ITALIAN_STOPWORD_THRESHOLD = 0.12   # 12% — Italian text typically 20-35%
GERMAN_STOPWORD_THRESHOLD = 0.12
SPANISH_STOPWORD_THRESHOLD = 0.12
DUTCH_STOPWORD_THRESHOLD = 0.12
PORTUGUESE_STOPWORD_THRESHOLD = 0.12


# ---------------------------------------------------------------------------
# Language Detection Functions
# ---------------------------------------------------------------------------

def is_language(
    text: str,
    stopwords: set[str],
    threshold: float,
    lang_label: str,
    short_default: bool = False,
) -> bool:
    """Unified language-detection heuristic.

    Samples the first ~2000 characters, tokenizes by whitespace,
    and checks what fraction of tokens are in the given *stopwords* set.
    *short_default* is returned when the sample is too short to judge
    (True for English so we don't block PII, False for others).
    """
    sample = text[:LANG_SAMPLE_SIZE]
    words = [w.lower().strip(".,;:!?()[]{}\"'") for w in sample.split()]
    words = [w for w in words if len(w) >= 2]  # drop 1-char tokens
    if len(words) < 20:
        return short_default
    stop_count = sum(1 for w in words if w in stopwords)
    ratio = stop_count / len(words)
    logger.debug(
        "%s language check: %d/%d words (%.1f%%) are stop words",
        lang_label, stop_count, len(words), ratio * 100,
    )
    return ratio >= threshold


def is_english_text(text: str) -> bool:
    """Check if text appears to be English based on stop word frequency."""
    return is_language(
        text, get_en_stop_lower(), ENGLISH_STOPWORD_THRESHOLD, "English", short_default=True
    )


def is_french_text(text: str) -> bool:
    """Check if text appears to be French based on stop word frequency."""
    return is_language(
        text, get_fr_stop_lower(), FRENCH_STOPWORD_THRESHOLD, "French"
    )


def is_italian_text(text: str) -> bool:
    """Check if text appears to be Italian based on stop word frequency."""
    return is_language(
        text, get_it_stop_lower(), ITALIAN_STOPWORD_THRESHOLD, "Italian"
    )


def is_german_text(text: str) -> bool:
    """Check if text appears to be German based on stop word frequency."""
    return is_language(
        text, get_de_stop_lower(), GERMAN_STOPWORD_THRESHOLD, "German"
    )


def is_spanish_text(text: str) -> bool:
    """Check if text appears to be Spanish based on stop word frequency."""
    return is_language(
        text, get_es_stop_lower(), SPANISH_STOPWORD_THRESHOLD, "Spanish"
    )


def is_dutch_text(text: str) -> bool:
    """Check if text appears to be Dutch based on stop word frequency."""
    return is_language(
        text, get_nl_stop_lower(), DUTCH_STOPWORD_THRESHOLD, "Dutch"
    )


def is_portuguese_text(text: str) -> bool:
    """Check if text appears to be Portuguese based on stop word frequency."""
    return is_language(
        text, get_pt_stop_lower(), PORTUGUESE_STOPWORD_THRESHOLD, "Portuguese"
    )
