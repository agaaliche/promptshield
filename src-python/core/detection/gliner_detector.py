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
# Model management (lazy-loaded singleton, thread-safe)
# ---------------------------------------------------------------------------

import threading

_model = None
_model_lock = threading.Lock()
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


def _load_model() -> object:
    """Lazy-load the GLiNER model (downloads on first use, ~500 MB).

    Thread-safe via double-checked locking.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
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
    """Return True if the GLiNER package is importable.

    This is a lightweight probe that does NOT trigger model download.
    """
    try:
        import gliner  # noqa: F401
        return True
    except ImportError:
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
    # ────────────────────────────────────────────────────────────────────────────
    # ENGLISH stopwords (from NER detector)
    # ────────────────────────────────────────────────────────────────────────────
    # Generic stopwords
    "q1", "q2", "q3", "q4", "fy", "ytd", "mtd",
    "n/a", "na", "tbd", "tba", "etc", "pdf", "doc",
    "inc", "llc", "ltd", "corp",
    "quarterly", "annual", "monthly", "weekly", "daily",
    "next", "last", "previous", "current", "recent",
    "today", "tomorrow", "yesterday",
    "above", "below", "total", "subtotal", "grand",
    # Person stopwords
    "the", "a", "an", "this", "that", "it", "i", "we", "you", "he", "she",
    "my", "your", "his", "her", "our", "their", "its",
    "mr", "mrs", "ms", "dr", "prof",
    "dear", "hi", "hello", "yes", "no", "ok", "please", "thank", "thanks",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "page", "section", "table", "figure", "chapter", "appendix",
    "total", "amount", "balance", "date", "number", "type",
    # Title suffixes (English job titles)
    "chairman", "chairwoman", "chairperson", "chair",
    "president", "vice", "director", "officer", "manager",
    "chief", "executive", "ceo", "cfo", "coo", "cto", "cio",
    "secretary", "treasurer", "counsel", "attorney",
    "partner", "associate", "analyst", "consultant",
    "md", "svp", "evp", "vp",
    "head", "lead", "senior", "junior",
    # ORG stopwords
    "department", "section", "division", "group", "team",
    "committee", "board", "council", "commission",
    "act", "law", "regulation", "policy", "standard",
    "agreement", "contract", "report", "summary",
    "schedule", "exhibit", "annex", "appendix",
    "article", "clause", "provision", "amendment",
    "chart", "graph",
    
    # ────────────────────────────────────────────────────────────────────────────
    # FRENCH stopwords (from NER detector)
    # ────────────────────────────────────────────────────────────────────────────
    # Person stopwords
    "monsieur", "madame", "mademoiselle", "mme", "mlle",
    "le", "la", "les", "un", "une", "des", "du", "de",
    "ce", "cette", "son", "sa", "ses", "notre", "votre", "leur",
    "il", "elle", "nous", "vous", "ils", "elles", "on",
    "pagina", "tabella", "figura", "capitolo", "allegato",
    "totale", "importo", "saldo", "data", "numero", "tipo",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
    "qui", "que", "où", "ou", "quoi", "dont", "avec", "sans", "pour", "par",
    "dans", "sur", "sous", "vers", "chez", "dès",
    # ORG stopwords
    "département", "departement", "service", "bureau", "direction",
    "division", "commission", "comité", "comite",
    "article", "clause", "alinéa", "alinea", "annexe",
    "tableau", "graphique",
    "loi", "décret", "decret", "arrêté", "arrete", "règlement", "reglement",
    "contrat", "accord", "convention", "rapport", "résumé", "resume",
    "principales", "principaux", "principale", "principal",
    "général", "generale", "generaux", "générale", "généraux",
    "comptables", "comptable", "comptabilité", "comptabilite",
    "financier", "financiere", "financiers", "financieres", "financière", "financières",
    "corporelles", "corporels", "corporel", "corporelle",
    "immobilisations", "immobilisation",
    "méthodes", "methodes", "méthode", "methode",
    "statuts", "statut", "nature", "activités", "activites", "activité", "activite",
    "éléments", "elements", "élément", "element",
    "informations", "information",
    "établissement", "etablissement", "établissements", "etablissements",
    "appliquée", "applique", "appliquées", "appliques", "appliqué", "appliqués",
    "opérations", "operations", "opération", "operation",
    "complémentaires", "complementaires", "complémentaire", "complementaire",
    "notes", "note",
    "société", "societe", "sociétés", "societes",
    # French generic business terms
    "entreprise", "compagnie", "filiale", "succursale",
    "conseil", "ministère", "ministere", "gouvernement",
    
    # ────────────────────────────────────────────────────────────────────────────
    # ITALIAN stopwords (from NER detector)
    # ────────────────────────────────────────────────────────────────────────────
    # Person stopwords
    "signor", "signore", "signora", "signorina", "sig", "dott", "avv",
    "lo", "gli", "i",
    "di", "del", "della", "dei", "delle", "dello",
    "questo", "questa", "suo", "sua", "loro", "nostro", "nostra",
    "lui", "lei", "noi", "voi", "essi", "esse",
    "pagina", "sezione", "tabella", "capitolo",
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    "lunedì", "lunedi", "martedì", "martedi", "mercoledì", "mercoledi",
    "giovedì", "giovedi", "venerdì", "venerdi", "sabato", "domenica",
    # ORG stopwords
    "dipartimento", "servizio", "ufficio", "direzione",
    "sezione", "articolo", "clausola", "allegato",
    "grafico",
    "legge", "decreto", "ordinanza", "regolamento",
    "contratto", "accordo", "convenzione", "rapporto", "relazione",
    
    # ────────────────────────────────────────────────────────────────────────────
    # GERMAN stopwords (basic set)
    # ────────────────────────────────────────────────────────────────────────────
    "gesellschaft", "unternehmen", "abteilung",
    
    # ────────────────────────────────────────────────────────────────────────────
    # SPANISH stopwords (basic set)
    # ────────────────────────────────────────────────────────────────────────────
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
    # Additional French accounting/business terms
    "comptabilité", "comptabilite", "informations", "information",
    "établissement", "etablissement", "établissements", "etablissements",
    "opérations", "operations", "opération", "operation",
    "notes", "note", "principales", "principaux", "principale", "principal",
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
