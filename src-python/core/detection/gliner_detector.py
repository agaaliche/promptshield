"""GLiNER-based multilingual PII detector.

GLiNER is a zero-shot NER model that works across languages.
We use the ``urchade/gliner_multi_pii-v1`` checkpoint which was
fine-tuned specifically for PII detection in 40+ languages.

This module is designed as a drop-in companion to the spaCy NER
detector.  It runs on **every** page regardless of language (unlike
the English-only spaCy layer) and is therefore the primary NER engine
for non-English documents.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from models.schemas import PIIType

logger = logging.getLogger(__name__)


class GLiNERMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# Model management (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_model = None
_MODEL_NAME = "urchade/gliner_multi_pii-v1"

# Labels we ask GLiNER to detect and their mapping to our PIIType enum.
_GLINER_LABELS: list[str] = [
    "person",
    "organization",
    "phone number",
    "email",
    "passport number",
    "credit card number",
    "social security number",
    "address",
    "date of birth",
    "location",
]

_LABEL_TO_PII: dict[str, PIIType] = {
    "person": PIIType.PERSON,
    "organization": PIIType.ORG,
    "phone number": PIIType.PHONE,
    "email": PIIType.EMAIL,
    "passport number": PIIType.PASSPORT,
    "credit card number": PIIType.CREDIT_CARD,
    "social security number": PIIType.SSN,
    "address": PIIType.ADDRESS,
    "date of birth": PIIType.DATE,
    "location": PIIType.LOCATION,
}

# Chunking — GLiNER typically handles up to ~512 tokens well.
# We chunk by characters with overlap to avoid splitting entities.
_CHUNK_SIZE = 3000      # ~512 tokens worth of chars
_CHUNK_OVERLAP = 200

# Minimum confidence from GLiNER to keep a match (model-level filter).
# Set low so GLiNER acts as a broad candidate generator — even a 0.20 hit
# provides valuable cross-layer confirmation that boosts LLM / regex matches
# past the pipeline's 0.55 display threshold.
_MIN_GLINER_SCORE = 0.20


def _load_model():
    """Lazy-load the GLiNER model (downloads on first use, ~500 MB)."""
    global _model
    if _model is not None:
        return _model

    try:
        from gliner import GLiNER
        logger.info("Loading GLiNER model '%s' …", _MODEL_NAME)
        _model = GLiNER.from_pretrained(_MODEL_NAME)
        logger.info("GLiNER model loaded successfully")
        return _model
    except Exception as e:
        logger.error("Failed to load GLiNER model: %s", e)
        raise


def is_gliner_available() -> bool:
    """Return True if GLiNER can be loaded without raising."""
    try:
        _load_model()
        return True
    except Exception:
        return False


def unload_model() -> None:
    """Free memory held by the loaded GLiNER model."""
    global _model
    _model = None
    logger.info("GLiNER model unloaded")


# ---------------------------------------------------------------------------
# False-positive filters
# ---------------------------------------------------------------------------

# French/international legal-form suffixes that should NOT be filtered
# when they appear as part of a multi-word company name (e.g. "Dupont SA").
_COMPANY_SUFFIXES: set[str] = {
    "sa", "sas", "sarl", "eurl", "sci", "snc", "se",
    "gmbh", "ag", "bv", "nv",
    "inc", "llc", "ltd", "corp", "co", "plc",
}

_FP_STOPWORDS: set[str] = {
    "total", "amount", "balance", "date", "number", "type", "page",
    "section", "table", "figure", "chapter", "appendix",
    "n/a", "na", "tbd", "tba", "etc", "pdf", "doc",
    # French generic business terms
    "société", "societe", "entreprise", "compagnie", "division",
    "filiale", "succursale", "direction", "comité", "comite",
    "conseil", "ministère", "ministere", "gouvernement",
    "département", "departement", "service", "bureau",
    # German
    "gesellschaft", "unternehmen", "abteilung",
    # Spanish
    "empresa", "compañía", "compania", "división",
}

# Single words that GLiNER often misclassifies as ORG
_ORG_NOISE_WORDS: set[str] = {
    "société", "societe", "division", "section", "groupe",
    "client", "fournisseur", "actif", "passif",
    "encaisse", "emprunt", "immobilisation", "amortissement",
    "solde", "fourn", "four", "court", "long",
    "exploitation", "financement", "investissement",
    # Partial French accounting terms
    "fr", "emp", "lo", "en", "per", "ex", "amor", "immob",
    "achats", "coût", "cout", "frais",
}


def _is_noise(text: str, pii_type: PIIType) -> bool:
    """Filter out obvious false positives."""
    clean = text.strip()
    low = clean.lower()

    # Too short
    if len(clean) < 2:
        return True
    # Pure digits shorter than 5 (not SSN/phone)
    if clean.isdigit() and len(clean) < 5:
        return True
    # Generic stopword (but not company suffixes — those are only noise alone)
    if low in _FP_STOPWORDS:
        return True
    # Company suffix alone (e.g. just "SA") — noise by itself
    if low in _COMPANY_SUFFIXES:
        return True
    # Single-char or single very short word
    words = clean.split()
    if len(words) == 1 and len(words[0]) <= 2:
        return True
    # Single-word ORG that's a generic business/accounting term
    if pii_type == PIIType.ORG and len(words) == 1 and low in _ORG_NOISE_WORDS:
        return True
    # Multi-word ORG: keep if at least one word is a real name
    # (capitalised and not a noise/stopword/suffix)
    if pii_type == PIIType.ORG and len(words) >= 2:
        has_real_word = any(
            w[0].isupper()
            and w.lower() not in _FP_STOPWORDS
            and w.lower() not in _ORG_NOISE_WORDS
            and w.lower() not in _COMPANY_SUFFIXES
            and len(w) > 2
            for w in words
        )
        if not has_real_word:
            return True
    return False


def _scale_confidence(raw_score: float, pii_type: PIIType | None = None) -> float:
    """Map GLiNER's raw score to a normalised confidence.

    GLiNER scores are calibrated differently from spaCy / regex.
    A GLiNER score of ~0.40 is already a decent signal.  We apply
    a linear mapping so that:
        raw 0.20 → 0.48  (weak candidate, needs cross-layer boost)
        raw 0.25 → 0.55  (just passes the pipeline threshold)
        raw 0.50 → 0.75
        raw 0.80 → 0.95
    """
    mapped = 0.48 + (raw_score - 0.20) * (0.95 - 0.48) / (0.80 - 0.20)
    return round(max(0.0, min(mapped, 0.95)), 4)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _process_chunk(
    model,
    text: str,
    global_offset: int,
) -> list[GLiNERMatch]:
    """Run GLiNER on a single text chunk."""
    entities = model.predict_entities(
        text,
        _GLINER_LABELS,
        threshold=_MIN_GLINER_SCORE,
    )

    matches: list[GLiNERMatch] = []
    for ent in entities:
        label = ent.get("label", "").lower()
        pii_type = _LABEL_TO_PII.get(label)
        if pii_type is None:
            continue

        ent_text = ent.get("text", "").strip()
        score = float(ent.get("score", 0.0))
        start = int(ent.get("start", 0))
        end = int(ent.get("end", start + len(ent_text)))

        if _is_noise(ent_text, pii_type):
            continue

        matches.append(GLiNERMatch(
            start=global_offset + start,
            end=global_offset + end,
            text=ent_text,
            pii_type=pii_type,
            confidence=_scale_confidence(score, pii_type),
        ))

    return matches


def _deduplicate(matches: list[GLiNERMatch]) -> list[GLiNERMatch]:
    """Remove duplicate/overlapping matches from chunk boundaries."""
    if not matches:
        return []
    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[GLiNERMatch] = [matches[0]]
    for m in matches[1:]:
        prev = deduped[-1]
        if m.start < prev.end:
            if m.confidence > prev.confidence or (m.end - m.start) > (prev.end - prev.start):
                deduped[-1] = m
        else:
            deduped.append(m)
    return deduped


def detect_gliner(text: str) -> list[GLiNERMatch]:
    """
    Run GLiNER multilingual PII detection on *text*.

    Works on any language.  Long texts are processed in overlapping
    chunks to stay within the model's context window.
    """
    if not text.strip():
        return []

    model = _load_model()

    # Short text — single pass
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk(model, text, global_offset=0)

    # Long text — sliding window
    all_matches: list[GLiNERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk(model, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate(all_matches)
