"""Shared text-normalisation helpers.

Centralises accent-stripping, whitespace collapsing, and other
text-cleaning utilities used by detection, propagation, and the
API layer.
"""

from __future__ import annotations

import re as _re
import unicodedata as _unicodedata

# ---------------------------------------------------------------------------
# Accent / diacritic stripping
# ---------------------------------------------------------------------------

# Explicit single-char replacements for ligatures & special chars whose
# NFD decomposition doesn't yield a clean base letter.
_SPECIAL: dict[str, str] = {
    "ß": "s", "ẞ": "S",  # German Eszett
    "æ": "a", "Æ": "A",  # Latin ligature AE
    "œ": "o", "Œ": "O",  # Latin ligature OE
    "ð": "d", "Ð": "D",  # Eth
    "þ": "t", "Þ": "T",  # Thorn
    "ø": "o", "Ø": "O",  # Scandinavian O-slash
    "đ": "d", "Đ": "D",  # Croatian D-stroke
    "ł": "l", "Ł": "L",  # Polish L-slash
    "ı": "i",             # Turkish dotless I
}


def strip_accents(text: str) -> str:
    """Strip diacritics/accents while preserving string length.

    Each original character maps to exactly one output character (the base
    letter without combining marks), so ``len(result) == len(text)`` and
    character-offset indices remain valid.

    Examples: é→e, ü→u, ñ→n, ö→o, ç→c, ß→s, æ→a, œ→o.
    """
    out: list[str] = []
    for ch in text:
        if ch in _SPECIAL:
            out.append(_SPECIAL[ch])
        else:
            nfd = _unicodedata.normalize("NFD", ch)
            base = "".join(c for c in nfd if _unicodedata.category(c) != "Mn")
            out.append(base if base else ch)
    return "".join(out)


def remove_accents(text: str) -> str:
    """Remove accents/diacritics via NFD decomposition.

    Simpler variant of :func:`strip_accents` — does **not** handle
    ligatures (ß, æ, œ …) and may change string length.  Prefer
    :func:`strip_accents` for offset-sensitive work.
    """
    nfkd = _unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if not _unicodedata.combining(c))


# ---------------------------------------------------------------------------
# Whitespace collapsing
# ---------------------------------------------------------------------------

def ws_collapse(text: str) -> str:
    """Collapse whitespace runs into single spaces and strip."""
    return _re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Combined normalisation
# ---------------------------------------------------------------------------

def normalize_for_matching(text: str) -> str:
    """Lowercase, strip accents (NFKD), collapse whitespace.

    Intended for fuzzy / highlight-all matching where offsets are
    not important.
    """
    text = _unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not _unicodedata.combining(c))
    text = text.lower()
    return _re.sub(r"\s+", " ", text).strip()
