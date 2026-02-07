"""Hugging Face BERT-based NER detector — alternative Layer 2 for the hybrid pipeline.

Supports three pre-trained models selectable via config:
  - dslim/bert-base-NER          — general NER (PER, ORG, LOC, MISC)
  - StanfordAIMI/stanford-deidentifier-base — clinical / medical de-identification
  - lakshyakh93/deberta_finetuned_pii       — PII-specific (names, emails, phones, etc.)

Texts are processed in overlapping chunks so accuracy stays high for long
documents.  The public API mirrors ``ner_detector`` so the pipeline can
swap between spaCy and BERT transparently.
"""

from __future__ import annotations

import logging
from typing import NamedTuple, Optional

from models.schemas import PIIType

logger = logging.getLogger(__name__)


class NERMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# Supported models and their entity-label → PIIType mappings
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: dict[str, dict] = {
    "dslim/bert-base-NER": {
        "description": "General NER (PER, ORG, LOC, MISC) — lightweight, fast",
        "label_map": {
            "PER": PIIType.PERSON,
            "ORG": PIIType.ORG,
            "LOC": PIIType.LOCATION,
            "MISC": PIIType.CUSTOM,
        },
    },
    "StanfordAIMI/stanford-deidentifier-base": {
        "description": "Clinical / medical de-identification",
        "label_map": {
            "PATIENT": PIIType.PERSON,
            "STAFF": PIIType.PERSON,
            "AGE": PIIType.DATE,
            "DATE": PIIType.DATE,
            "PHONE": PIIType.PHONE,
            "ID": PIIType.CUSTOM,
            "EMAIL": PIIType.EMAIL,
            "PATORG": PIIType.ORG,
            "HOSPITAL": PIIType.ORG,
            "OTHERPHI": PIIType.CUSTOM,
            "LOC": PIIType.LOCATION,
            "LOCATION": PIIType.LOCATION,
            "HCW": PIIType.PERSON,
            "VENDOR": PIIType.ORG,
        },
    },
    "lakshyakh93/deberta_finetuned_pii": {
        "description": "PII-specific (names, emails, phones, addresses, etc.)",
        "label_map": {
            "NAME_STUDENT": PIIType.PERSON,
            "EMAIL": PIIType.EMAIL,
            "USERNAME": PIIType.PERSON,
            "ID_NUM": PIIType.CUSTOM,
            "PHONE_NUM": PIIType.PHONE,
            "URL_PERSONAL": PIIType.CUSTOM,
            "STREET_ADDRESS": PIIType.ADDRESS,
        },
    },
}

# ---------------------------------------------------------------------------
# Module-level state (lazy-loaded)
# ---------------------------------------------------------------------------

_pipeline = None
_active_model_id: str = ""
_label_map: dict[str, PIIType] = {}

# Chunking parameters
_CHUNK_SIZE = 10_000       # characters per chunk (BERT tokeniser limit ~512 tokens ≈ 2-3k chars)
_CHUNK_OVERLAP = 300       # overlap in characters


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_pipeline(model_id: str | None = None):
    """Lazy-load a Hugging Face token-classification pipeline."""
    global _pipeline, _active_model_id, _label_map

    if model_id is None:
        from core.config import config
        model_id = config.ner_hf_model

    if _pipeline is not None and _active_model_id == model_id:
        return _pipeline

    from transformers import pipeline as hf_pipeline

    logger.info(f"Loading HF NER model '{model_id}' …")
    model_info = AVAILABLE_MODELS.get(model_id)
    if model_info is None:
        raise ValueError(
            f"Unknown BERT NER model '{model_id}'. "
            f"Available: {', '.join(AVAILABLE_MODELS)}"
        )

    _pipeline = hf_pipeline(
        "ner",
        model=model_id,
        aggregation_strategy="simple",
        device=-1,                    # CPU; set 0 for GPU
    )
    _active_model_id = model_id
    _label_map = model_info["label_map"]
    logger.info(f"HF model '{model_id}' loaded successfully")
    return _pipeline


def unload_pipeline() -> None:
    """Free memory held by the current HF model."""
    global _pipeline, _active_model_id, _label_map
    _pipeline = None
    _active_model_id = ""
    _label_map = {}
    logger.info("HF NER pipeline unloaded")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _process_chunk(pipe, text: str, global_offset: int) -> list[NERMatch]:
    """Run the HF pipeline on a single chunk and yield NERMatch instances."""
    results = pipe(text)
    matches: list[NERMatch] = []

    for ent in results:
        # ``aggregation_strategy="simple"`` gives keys:
        #   entity_group, score, word, start, end
        raw_label: str = ent.get("entity_group", "")
        score: float = ent.get("score", 0.0)
        start: int = ent.get("start", 0)
        end: int = ent.get("end", 0)
        word: str = ent.get("word", text[start:end])

        pii_type = _label_map.get(raw_label)
        if pii_type is None:
            continue
        if len(word.strip()) < 2:
            continue

        matches.append(NERMatch(
            start=global_offset + start,
            end=global_offset + end,
            text=word,
            pii_type=pii_type,
            confidence=round(score, 4),
        ))

    return matches


def _deduplicate_matches(matches: list[NERMatch]) -> list[NERMatch]:
    """Remove duplicates arising from overlapping chunks."""
    if not matches:
        return []

    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[NERMatch] = [matches[0]]

    for m in matches[1:]:
        prev = deduped[-1]
        if m.start < prev.end:
            if m.confidence > prev.confidence or (m.end - m.start) > (prev.end - prev.start):
                deduped[-1] = m
        else:
            deduped.append(m)

    return deduped


def detect_bert_ner(text: str, model_id: str | None = None) -> list[NERMatch]:
    """
    Run Hugging Face BERT NER on *text* and return PII matches.

    Long texts are split into overlapping chunks to stay within the
    model's context window.
    """
    pipe = _load_pipeline(model_id)

    if len(text) <= _CHUNK_SIZE:
        return _process_chunk(pipe, text, global_offset=0)

    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk(pipe, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)

        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# Introspection helpers (used by API / settings)
# ---------------------------------------------------------------------------

def get_active_model_id() -> str:
    """Return the currently loaded HF model id, or ``""``."""
    return _active_model_id


def is_bert_ner_available() -> bool:
    """Check if a BERT NER pipeline can be loaded (transformers installed)."""
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def list_available_bert_models() -> list[dict]:
    """Return metadata for all supported BERT NER models."""
    return [
        {"model_id": mid, "description": info["description"]}
        for mid, info in AVAILABLE_MODELS.items()
    ]
