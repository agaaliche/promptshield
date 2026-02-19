"""spaCy NER-based PII detector — Layer 2 of the hybrid pipeline.

Detects named entities: PERSON, ORG, GPE, DATE, LOC, MONEY, etc.
Supports transformer models (en_core_web_trf) for highest accuracy,
with automatic fallback to lg → sm.  Long texts are processed in
overlapping chunks so NER quality stays high.

When no spaCy model is available, a lightweight heuristic name
detector provides basic name coverage as a fallback.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Callable, NamedTuple

from models.schemas import PIIType

# Import from split-out modules (M8: modular NER architecture)
from core.detection.ner_types import (
    NERMatch,
    LangNERConfig as _LangNERConfig,
    SPACY_EN_LABEL_MAP,
    SPACY_FR_LABEL_MAP,
    SPACY_IT_LABEL_MAP,
    SPACY_DE_LABEL_MAP,
    SPACY_ES_LABEL_MAP,
    SPACY_NL_LABEL_MAP,
    SPACY_PT_LABEL_MAP,
    MIN_ENTITY_LENGTH,
)
from core.detection.ner_stopwords import (
    get_en_stop_words as _get_en_stop_words,
    get_fr_stop_words as _get_fr_stop_words,
    get_it_stop_words as _get_it_stop_words,
    get_de_stop_words as _get_de_stop_words,
    get_es_stop_words as _get_es_stop_words,
    get_nl_stop_words as _get_nl_stop_words,
    get_pt_stop_words as _get_pt_stop_words,
    get_en_stop_lower as _get_en_stop_lower,
    get_fr_stop_lower as _get_fr_stop_lower,
    get_it_stop_lower as _get_it_stop_lower,
    get_de_stop_lower as _get_de_stop_lower,
    get_es_stop_lower as _get_es_stop_lower,
    get_nl_stop_lower as _get_nl_stop_lower,
    get_pt_stop_lower as _get_pt_stop_lower,
    is_language as _is_language,
    is_english_text as _is_english_text,
    is_french_text as _is_french_text,
    is_italian_text as _is_italian_text,
    is_german_text as _is_german_text,
    is_spanish_text as _is_spanish_text,
    is_dutch_text as _is_dutch_text,
    is_portuguese_text as _is_portuguese_text,
    LANG_SAMPLE_SIZE as _LANG_SAMPLE_SIZE,
    ENGLISH_STOPWORD_THRESHOLD as _ENGLISH_STOPWORD_THRESHOLD,
    FRENCH_STOPWORD_THRESHOLD as _FRENCH_STOPWORD_THRESHOLD,
    ITALIAN_STOPWORD_THRESHOLD as _ITALIAN_STOPWORD_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Re-export label maps with original names for backward compatibility
_SPACY_LABEL_MAP = SPACY_EN_LABEL_MAP
_SPACY_FR_LABEL_MAP = SPACY_FR_LABEL_MAP
_SPACY_IT_LABEL_MAP = SPACY_IT_LABEL_MAP
_SPACY_DE_LABEL_MAP = SPACY_DE_LABEL_MAP
_SPACY_ES_LABEL_MAP = SPACY_ES_LABEL_MAP
_SPACY_NL_LABEL_MAP = SPACY_NL_LABEL_MAP
_SPACY_PT_LABEL_MAP = SPACY_PT_LABEL_MAP
_MIN_ENTITY_LENGTH = MIN_ENTITY_LENGTH

# ---------------------------------------------------------------------------
# False-positive filters and stopwords (PII detection specific)
# ---------------------------------------------------------------------------

# Common false-positive strings for PERSON type
_PERSON_STOPWORDS: set[str] = {
    "the", "a", "an", "this", "that", "it", "i", "we", "you", "he", "she",
    "my", "your", "his", "her", "our", "their", "its",
    "mr", "mrs", "ms", "dr", "prof",  # titles alone without a name
    "dear", "hi", "hello", "yes", "no", "ok", "please", "thank", "thanks",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "page", "section", "table", "figure", "chapter", "appendix",
    "total", "amount", "balance", "date", "number", "type",
}

# Job titles / roles that spaCy often appends to PERSON entities
_TITLE_SUFFIXES: set[str] = {
    "chairman", "chairwoman", "chairperson", "chair",
    "president", "vice", "director", "officer", "manager",
    "chief", "executive", "ceo", "cfo", "coo", "cto", "cio",
    "secretary", "treasurer", "counsel", "attorney",
    "partner", "associate", "analyst", "consultant",
    "md", "svp", "evp", "vp",
    "head", "lead", "senior", "junior",
}

# Strings that NER models frequently misclassify for ORG/DATE/LOC
_GENERIC_STOPWORDS: set[str] = {
    "q1", "q2", "q3", "q4", "fy", "ytd", "mtd",
    "n/a", "na", "tbd", "tba", "etc", "pdf", "doc",
    "inc", "llc", "ltd", "corp",  # too short to be useful alone
    "quarterly", "annual", "monthly", "weekly", "daily",
    "next", "last", "previous", "current", "recent",
    "today", "tomorrow", "yesterday",
    "above", "below", "total", "subtotal", "grand",
}

# Common false-positive strings for ORG type
_ORG_STOPWORDS: set[str] = {
    "inc", "llc", "ltd", "corp", "co", "plc",
    "department", "section", "division", "group", "team",
    "committee", "board", "council", "commission",
    "act", "law", "regulation", "policy", "standard",
    "agreement", "contract", "report", "summary",
    "schedule", "exhibit", "annex", "appendix",
    "article", "clause", "provision", "amendment",
    "table", "figure", "chart", "graph",
}

# spaCy model (lazy-loaded)
_nlp = None
_active_model_name: str = ""

# French spaCy model (lazy-loaded separately)
_nlp_fr = None
_active_fr_model_name: str = ""

# Italian spaCy model (lazy-loaded separately)
_nlp_it = None
_active_it_model_name: str = ""

# German spaCy model (lazy-loaded separately)
_nlp_de = None
_active_de_model_name: str = ""

# Spanish spaCy model (lazy-loaded separately)
_nlp_es = None
_active_es_model_name: str = ""

# Dutch spaCy model (lazy-loaded separately)
_nlp_nl = None
_active_nl_model_name: str = ""

# Portuguese spaCy model (lazy-loaded separately)
_nlp_pt = None
_active_pt_model_name: str = ""

# Lock protecting lazy model initialisation (all languages)
_model_lock = threading.Lock()

# Model cascade order depending on user preference
_MODEL_CASCADE: dict[str, list[str]] = {
    "trf": ["en_core_web_trf", "en_core_web_lg", "en_core_web_sm"],
    "lg":  ["en_core_web_lg", "en_core_web_sm"],
    "sm":  ["en_core_web_sm"],
}

# French model cascade (best available → smallest fallback)
_FR_MODEL_CASCADE: list[str] = [
    "fr_core_news_lg",
    "fr_core_news_md",
    "fr_core_news_sm",
]

# Italian model cascade (best available → smallest fallback)
_IT_MODEL_CASCADE: list[str] = [
    "it_core_news_lg",
    "it_core_news_md",
    "it_core_news_sm",
]

# German model cascade (best available → smallest fallback)
_DE_MODEL_CASCADE: list[str] = [
    "de_core_news_lg",
    "de_core_news_md",
    "de_core_news_sm",
]

# Spanish model cascade (best available → smallest fallback)
_ES_MODEL_CASCADE: list[str] = [
    "es_core_news_lg",
    "es_core_news_md",
    "es_core_news_sm",
]

# Dutch model cascade (best available → smallest fallback)
_NL_MODEL_CASCADE: list[str] = [
    "nl_core_news_lg",
    "nl_core_news_md",
    "nl_core_news_sm",
]

# Portuguese model cascade (best available → smallest fallback)
_PT_MODEL_CASCADE: list[str] = [
    "pt_core_news_lg",
    "pt_core_news_md",
    "pt_core_news_sm",
]

# Chunking parameters (in characters)
_CHUNK_SIZE = 100_000          # Process in 100k-char chunks
_CHUNK_OVERLAP = 500           # 500-char overlap so entities at boundaries aren't lost


def _load_model() -> object:
    """Lazy-load the best available spaCy model based on config preference.

    Thread-safe: uses ``_model_lock`` so concurrent requests don't race.
    Will NOT auto-download models at runtime — raises RuntimeError if
    none are installed.
    """
    global _nlp, _active_model_name
    if _nlp is not None:  # fast path — no lock needed once loaded
        return _nlp

    with _model_lock:
        # Double-check after acquiring lock
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

        raise RuntimeError(
            "No spaCy NER model available. Install one with: "
            "python -m spacy download en_core_web_lg"
        )


def _load_french_model() -> object | None:
    """Lazy-load the best available French spaCy model.

    Thread-safe via ``_model_lock``.  Will NOT auto-download.
    Returns None if no French model is installed.
    """
    global _nlp_fr, _active_fr_model_name
    if _nlp_fr is not None:
        return _nlp_fr

    with _model_lock:
        if _nlp_fr is not None:
            return _nlp_fr

        import spacy

        for model_name in _FR_MODEL_CASCADE:
            try:
                _nlp_fr = spacy.load(model_name)
                _active_fr_model_name = model_name
                logger.info(f"Loaded French spaCy model '{model_name}'")
                return _nlp_fr
            except OSError:
                logger.info(f"French spaCy model '{model_name}' not installed — trying next")

        logger.warning("No French spaCy model found. Install with: python -m spacy download fr_core_news_lg")
        return None


def is_french_ner_available() -> bool:
    """Check whether a French NER model can be loaded."""
    try:
        return _load_french_model() is not None
    except BaseException:
        return False


# ── Unified false-positive helpers (M7: dedup EN/FR/IT) ──────────

def _is_false_positive_person_generic(text: str, stopwords: set[str]) -> bool:
    """Return True if a PERSON entity is likely a false positive.

    Shared logic for all languages — only the *stopwords* set differs.
    """
    clean = text.strip().lower()
    if clean in stopwords:
        return True
    if text.isupper() and len(text) <= 5:
        return True
    if text.strip() and text.strip()[0].isdigit():
        return True
    words = text.strip().split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    return False


def _is_false_positive_org_generic(
    text: str,
    org_stopwords: set[str],
    generic_stopwords: set[str] | None = None,
) -> bool:
    """Return True if an ORG entity is likely a false positive.

    Shared logic for all languages.  *generic_stopwords* is only used by
    English (pass ``None`` for FR/IT).
    """
    clean = text.strip()
    low = clean.lower()
    if low in org_stopwords:
        return True
    if generic_stopwords and low in generic_stopwords:
        return True
    if len(clean) <= 2:
        return True
    if clean.isupper() and len(clean) <= 4:
        return True
    # Pure digits / punctuation — never an org name (e.g. "195", "4002")
    if clean.isdigit():
        return True
    if clean and clean[0].isdigit():
        return True
    # All-lowercase single/two-word — real org names are capitalised
    words = clean.split()
    if clean == low and len(words) <= 2:
        return True
    return False


def _is_false_positive_person(text: str) -> bool:
    return _is_false_positive_person_generic(text, _PERSON_STOPWORDS)


def _is_false_positive_org(text: str) -> bool:
    return _is_false_positive_org_generic(text, _ORG_STOPWORDS, _GENERIC_STOPWORDS)


# ── Per-language NER configuration (M7: dedup EN/FR/IT) ──────────
# _LangNERConfig is imported from ner_types module


def _get_active_en_model() -> str:
    return _active_model_name


def _get_active_fr_model() -> str:
    return _active_fr_model_name


def _get_active_it_model() -> str:
    return _active_it_model_name


def _get_active_de_model() -> str:
    return _active_de_model_name


def _get_active_es_model() -> str:
    return _active_es_model_name


def _get_active_nl_model() -> str:
    return _active_nl_model_name


def _get_active_pt_model() -> str:
    return _active_pt_model_name


_EN_CONFIG = _LangNERConfig(
    label_map=_SPACY_LABEL_MAP,
    article_prefixes=("the ", "The ", "a ", "A ", "an ", "An "),
    strip_title_suffixes=True,
    fp_person=_is_false_positive_person,
    fp_org=_is_false_positive_org,
    generic_stopwords_filter=True,
    active_model_name=_get_active_en_model,
    base_confidence={
        PIIType.PERSON: 0.80, PIIType.ORG: 0.40,
        PIIType.LOCATION: 0.25, PIIType.ADDRESS: 0.55,
    },
    person_multiword_cap=0.95,
    org_3word_cap=0.80,
    person_single_penalty=0.20,
    org_single_floor=0.25,
    model_boost_tiers=(("_trf", 0.08, 0.98), ("_lg", 0.03, 0.95)),
)


# ── Unified _process_chunk / _estimate_confidence (M7) ──────────

def _process_chunk_generic(
    nlp, text: str, global_offset: int, cfg: _LangNERConfig,
) -> list[NERMatch]:
    """Run NER on a single text chunk — shared logic for all languages."""
    doc = nlp(text)
    matches: list[NERMatch] = []

    for ent in doc.ents:
        pii_type = cfg.label_map.get(ent.label_)
        if pii_type is None:
            continue

        raw_text = ent.text
        nl_idx = raw_text.find("\n")
        if nl_idx > 0:
            raw_text = raw_text[:nl_idx]
        cleaned = raw_text.strip()

        # Strip leading articles
        for prefix in cfg.article_prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        # For ORG entities, strip leading company-context words
        # (e.g., FR "société X" → "X", "compagnie Y" → "Y")
        if pii_type == PIIType.ORG and cfg.org_context_prefixes:
            for ctx_prefix in cfg.org_context_prefixes:
                if cleaned.lower().startswith(ctx_prefix.lower()):
                    cleaned = cleaned[len(ctx_prefix):].strip()
                    break

        # For PERSON entities, trim trailing job titles (EN only)
        if cfg.strip_title_suffixes and pii_type == PIIType.PERSON:
            words = cleaned.split()
            while len(words) > 2 and words[-1].lower() in _TITLE_SUFFIXES:
                words.pop()
            cleaned = " ".join(words)

        min_len = _MIN_ENTITY_LENGTH.get(pii_type, 2)
        if len(cleaned) < min_len:
            continue

        if pii_type == PIIType.PERSON and cfg.fp_person(cleaned):
            continue
        if pii_type == PIIType.ORG and cfg.fp_org(cleaned):
            continue

        # Generic noise filters
        if cleaned.isupper() and len(cleaned) <= 5:
            continue
        if cleaned.isdigit():
            continue
        if cfg.generic_stopwords_filter and cleaned.lower() in _GENERIC_STOPWORDS:
            continue

        # Compute char offsets from the original entity span but
        # advance start when article/context prefixes were stripped so
        # the bbox covers only the cleaned text.
        prefix_stripped = len(ent.text) - len(ent.text.lstrip()) + (
            len(ent.text.lstrip()) - len(raw_text)
            if len(ent.text.lstrip()) > len(raw_text) else 0
        )
        # Additionally account for article and context prefix stripping:
        # cleaned starts after those prefixes relative to raw_text.
        offset_in_raw = raw_text.find(cleaned) if cleaned in raw_text else 0
        start_char = ent.start_char + offset_in_raw
        end_char = start_char + len(cleaned)
        confidence = _estimate_confidence_generic(ent, pii_type, cfg)
        matches.append(NERMatch(
            start=global_offset + start_char,
            end=global_offset + end_char,
            text=cleaned,
            pii_type=pii_type,
            confidence=confidence,
        ))

    return matches


def _estimate_confidence_generic(ent, pii_type: PIIType, cfg: _LangNERConfig) -> float:
    """Estimate confidence for a spaCy entity — shared logic for all languages."""
    conf = cfg.base_confidence.get(pii_type, 0.40)

    text = ent.text.strip()
    word_count = len(text.split())

    if word_count >= 2 and pii_type == PIIType.PERSON:
        conf = min(conf + 0.08, cfg.person_multiword_cap)
    if word_count >= 2 and pii_type == PIIType.ORG:
        conf = min(conf + 0.15, 0.80)
    if word_count >= 3 and pii_type == PIIType.ORG:
        conf = min(conf + 0.05, cfg.org_3word_cap)

    if pii_type == PIIType.PERSON and word_count == 1:
        conf = max(conf - cfg.person_single_penalty, 0.40)
    if pii_type == PIIType.ORG and word_count == 1:
        conf = max(conf - 0.15, cfg.org_single_floor)
    if pii_type == PIIType.LOCATION and word_count == 1:
        conf = max(conf - 0.10, 0.30)

    model_name = cfg.active_model_name()
    for suffix, delta, cap in cfg.model_boost_tiers:
        if model_name.endswith(suffix):
            conf = min(conf + delta, cap)
            break

    return round(conf, 4)


def _process_chunk(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _EN_CONFIG)


def _estimate_confidence(ent, pii_type: PIIType) -> float:
    return _estimate_confidence_generic(ent, pii_type, _EN_CONFIG)


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
    Skips detection entirely if the text does not appear to be English,
    since the English NER model produces only noise on other languages.
    """
    if not _is_english_text(text):
        logger.info("Text does not appear to be English — skipping NER")
        return []

    nlp = _load_model()

    # Short texts — single pass (fast path)
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk(nlp, text, global_offset=0)

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


# ---------------------------------------------------------------------------
# French spaCy NER entity label map
# ---------------------------------------------------------------------------
# French spaCy models use PER (not PERSON), ORG, LOC, MISC.

_SPACY_FR_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    # MISC intentionally omitted — too noisy (adjectives, demonyms, etc.)
}

# French-specific false-positive filters
_FR_PERSON_STOPWORDS: set[str] = {
    "monsieur", "madame", "mademoiselle", "mme", "mlle",
    "le", "la", "les", "un", "une", "des", "du", "de",
    "ce", "cette", "son", "sa", "ses", "notre", "votre", "leur",
    "il", "elle", "nous", "vous", "ils", "elles", "on",
    "page", "section", "tableau", "figure", "chapitre", "annexe",
    "total", "montant", "solde", "date", "numéro", "numero", "type",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
    # Common vocabulary
    "qui", "que", "où", "ou", "quoi", "dont", "avec", "sans", "pour", "par",
    "dans", "sur", "sous", "vers", "chez", "dès", "des",
    # French accounting / financial terms (never person names)
    "mobilier", "immobilier",
    "taux", "bilan", "exercice",
    "actif", "passif", "capital",
    "emprunt", "crédit", "credit", "débit", "debit",
    "amortissement", "amortissements",
    "provision", "provisions",
    "dotation", "dotations",
    "reprise", "reprises",
    "charge", "charges", "produit", "produits",
    "recette", "recettes",
    "facture", "factures",
    "titre", "titres", "fonds", "caisse",
    "valeur", "valeurs",
    "compte", "comptes",
    "poste", "postes",
    "dette", "dettes",
    "résultat", "resultat",
    "location", "acquisition",
    "location-acquisition", "lave-vaisselle",
}

_FR_ORG_STOPWORDS: set[str] = {
    "département", "departement", "service", "bureau", "direction",
    "section", "division", "commission", "comité", "comite",
    "article", "clause", "alinéa", "alinea", "annexe",
    "tableau", "figure", "graphique",
    "loi", "décret", "decret", "arrêté", "arrete", "règlement", "reglement",
    "contrat", "accord", "convention", "rapport", "résumé", "resume",
    # Common adjectives/nouns often misclassified
    "principales", "principaux", "général", "generale", "generaux",
    "comptables", "comptable", "financier", "financiere", "financiers", "financieres",
    "corporelles", "corporels", "corporel", "corporelle",
    "immobilisations", "immobilisation",
    "méthodes", "methodes", "méthode", "methode",
    "statuts", "statut", "nature", "activités", "activites", "activité", "activite",
    "éléments", "elements", "élément", "element",
    "société", "societe", "sociétés", "societes",
    "elles", "ils", "elle", "il", "nous", "vous",  # pronouns sometimes tagged as ORG
    "je", "tu", "on",
    # French accounting / financial terms
    "excédent", "excedent", "clos", "clôt",
    "taux", "location", "acquisition", "acquisitions",
    "location-acquisition", "lave-vaisselle",
    "dotation", "dotations", "reprise", "reprises",
    "écart", "ecart", "écarts", "ecarts",
    "valeur", "valeurs", "emprunt", "emprunts",
    "titre", "titres", "fonds", "caisse",
    "trésorerie", "tresorerie",
    "recette", "recettes", "facture", "factures",
    "poste", "postes", "créance", "creance",
    "dette", "dettes", "subvention", "subventions",
    "mobilier", "immobilier",
}


def _is_false_positive_person_fr(text: str) -> bool:
    """Return True if a French PERSON entity is likely a false positive."""
    if _is_false_positive_person_generic(text, _FR_PERSON_STOPWORDS):
        return True
    # French pronoun (+ optional contraction) + verb → never a person name.
    # Catches: "Nous n'avons", "nous n'exprimons", "Il est", "Elle a", etc.
    clean = text.strip()
    words = clean.split()
    if len(words) >= 2:
        first = words[0].lower().rstrip("'\u2019")
        if first in {
            "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
            "ce", "c", "ça", "cela", "ceci",
        }:
            return True
    return False


def _is_false_positive_org_fr(text: str) -> bool:
    """Return True if a French ORG entity is likely a false positive."""
    if _is_false_positive_org_generic(text, _FR_ORG_STOPWORDS, _GENERIC_STOPWORDS):
        return True
    # French pronoun (+ optional contraction) + verb → never an org name.
    # Catches: "Nous n'avons", "nous n'exprimons", "Il est", etc.
    clean = text.strip()
    words = clean.split()
    if len(words) >= 2:
        first = words[0].lower().rstrip("'\u2019")
        if first in {
            "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
            "ce", "c", "ça", "cela", "ceci",
        }:
            return True
    return False


_FR_CONFIG = _LangNERConfig(
    label_map=_SPACY_FR_LABEL_MAP,
    article_prefixes=(
        "le ", "Le ", "la ", "La ", "l'", "L'",
        "les ", "Les ", "un ", "Un ", "une ", "Une ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_fr,
    fp_org=_is_false_positive_org_fr,
    generic_stopwords_filter=False,
    active_model_name=_get_active_fr_model,
    org_context_prefixes=(
        "société ", "societe ", "sociétés ", "societes ",
    ),
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_fr(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _FR_CONFIG)


def _estimate_confidence_fr(ent, pii_type: PIIType) -> float:
    return _estimate_confidence_generic(ent, pii_type, _FR_CONFIG)


def detect_ner_french(text: str) -> list[NERMatch]:
    """
    Run French spaCy NER on text.

    Only runs if the text appears to be French.  Handles chunking
    for long texts the same way as the English detector.
    """
    if not _is_french_text(text):
        logger.info("Text does not appear to be French — skipping French NER")
        return []

    nlp = _load_french_model()
    if nlp is None:
        logger.info("No French spaCy model available — skipping French NER")
        return []

    # Short texts — single pass
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_fr(nlp, text, global_offset=0)

    # Long texts — overlapping sliding-window
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk_fr(nlp, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# Italian spaCy NER
# ---------------------------------------------------------------------------
# Italian spaCy models use PER (not PERSON), ORG, LOC — same as French.

_SPACY_IT_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    # MISC intentionally omitted — too noisy (adjectives, demonyms, etc.)
}

# Italian-specific false-positive filters
_IT_PERSON_STOPWORDS: set[str] = {
    "signor", "signore", "signora", "signorina", "sig", "dott", "avv",
    "il", "lo", "la", "le", "gli", "un", "uno", "una",
    "di", "del", "della", "dei", "delle", "dello",
    "questo", "questa", "suo", "sua", "loro", "nostro", "nostra",
    "lui", "lei", "noi", "voi", "essi", "esse",
    "pagina", "sezione", "tabella", "figura", "capitolo", "allegato",
    "totale", "importo", "saldo", "data", "numero", "tipo",
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    "lunedì", "lunedi", "martedì", "martedi", "mercoledì", "mercoledi",
    "giovedì", "giovedi", "venerdì", "venerdi", "sabato", "domenica",
}

_IT_ORG_STOPWORDS: set[str] = {
    "dipartimento", "servizio", "ufficio", "direzione",
    "sezione", "divisione", "commissione", "comitato",
    "articolo", "clausola", "allegato",
    "tabella", "figura", "grafico",
    "legge", "decreto", "ordinanza", "regolamento",
    "contratto", "accordo", "convenzione", "rapporto", "relazione",
}


def _load_italian_model() -> object | None:
    """Lazy-load the best available Italian spaCy model.

    Thread-safe via ``_model_lock``.  Will NOT auto-download.
    Returns None if no Italian model is installed.
    """
    global _nlp_it, _active_it_model_name
    if _nlp_it is not None:
        return _nlp_it

    with _model_lock:
        if _nlp_it is not None:
            return _nlp_it

        import spacy

        for model_name in _IT_MODEL_CASCADE:
            try:
                _nlp_it = spacy.load(model_name)
                _active_it_model_name = model_name
                logger.info(f"Loaded Italian spaCy model '{model_name}'")
                return _nlp_it
            except OSError:
                logger.info(f"Italian spaCy model '{model_name}' not installed — trying next")

        logger.warning("No Italian spaCy model found. Install with: python -m spacy download it_core_news_lg")
        return None


def is_italian_ner_available() -> bool:
    """Check whether an Italian NER model can be loaded."""
    try:
        return _load_italian_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_it(text: str) -> bool:
    """Return True if an Italian PERSON entity is likely a false positive."""
    return _is_false_positive_person_generic(text, _IT_PERSON_STOPWORDS)


def _is_false_positive_org_it(text: str) -> bool:
    """Return True if an Italian ORG entity is likely a false positive."""
    return _is_false_positive_org_generic(text, _IT_ORG_STOPWORDS, _GENERIC_STOPWORDS)


_IT_CONFIG = _LangNERConfig(
    label_map=_SPACY_IT_LABEL_MAP,
    article_prefixes=(
        "il ", "Il ", "lo ", "Lo ", "la ", "La ", "l'", "L'",
        "le ", "Le ", "gli ", "Gli ", "i ", "I ",
        "un ", "Un ", "uno ", "Uno ", "una ", "Una ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_it,
    fp_org=_is_false_positive_org_it,
    generic_stopwords_filter=False,
    active_model_name=_get_active_it_model,
    org_context_prefixes=(
        "società ", "societa ",
    ),
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_it(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _IT_CONFIG)


def _estimate_confidence_it(ent, pii_type: PIIType) -> float:
    return _estimate_confidence_generic(ent, pii_type, _IT_CONFIG)


def detect_ner_italian(text: str) -> list[NERMatch]:
    """
    Run Italian spaCy NER on text.

    Only runs if the text appears to be Italian.  Handles chunking
    for long texts the same way as the English/French detectors.
    """
    if not _is_italian_text(text):
        logger.info("Text does not appear to be Italian — skipping Italian NER")
        return []

    nlp = _load_italian_model()
    if nlp is None:
        logger.info("No Italian spaCy model available — skipping Italian NER")
        return []

    # Short texts — single pass
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_it(nlp, text, global_offset=0)

    # Long texts — overlapping sliding-window
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk_it(nlp, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# German spaCy NER
# ---------------------------------------------------------------------------
# German spaCy models use PER, ORG, LOC, MISC — same label scheme as FR/IT.

_SPACY_DE_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    # MISC intentionally omitted — too noisy
}

# German-specific false-positive filters
_DE_PERSON_STOPWORDS: set[str] = {
    "herr", "frau", "doktor", "professor",
    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "einer", "einem", "einen", "eines",
    "er", "sie", "es", "wir", "ihr",
    "sein", "seine", "seiner", "seinem", "seinen",
    "ihr", "ihre", "ihrem", "ihren", "ihrer",
    "mein", "meine", "meinem", "meinen", "meiner",
    "unser", "unsere", "unserem", "unseren", "unserer",
    "dieser", "diese", "dieses", "diesem", "diesen",
    "seite", "abschnitt", "tabelle", "abbildung", "kapitel", "anhang",
    "gesamt", "betrag", "saldo", "datum", "nummer", "typ",
    "januar", "februar", "märz", "maerz", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "dezember",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
    # Financial terms
    "bilanz", "gewinn", "verlust", "ertrag", "aufwand",
    "abschreibung", "abschreibungen",
    "rückstellung", "rueckstellung", "rückstellungen", "rueckstellungen",
    "vermögen", "vermoegen", "kapital",
    "steuer", "steuern", "dividende", "dividenden",
    "zins", "zinsen", "saldo", "betrag",
    "konto", "konten", "kasse",
    "umsatz", "kosten",
}

_DE_ORG_STOPWORDS: set[str] = {
    "abteilung", "bereich", "referat", "amt",
    "abschnitt", "absatz", "paragraph",
    "tabelle", "abbildung", "grafik", "diagramm",
    "gesetz", "verordnung", "erlass", "satzung", "beschluss",
    "vertrag", "vereinbarung", "abkommen",
    "bericht", "zusammenfassung", "gutachten",
    # Financial terms
    "bilanz", "gewinn", "verlust", "ertrag", "erträge", "ertraege",
    "aufwand", "aufwendungen", "kosten",
    "abschreibung", "abschreibungen",
    "rückstellung", "rueckstellung",
    "vermögen", "vermoegen",
    "eigenkapital", "fremdkapital",
    "jahresabschluss", "lagebericht",
    "anlage", "anlagen", "anlagevermögen", "anlagevermoegen",
    "umlaufvermögen", "umlaufvermoegen",
    "forderungen", "forderung",
    "verbindlichkeiten", "verbindlichkeit",
    "inventar", "vorräte", "vorraete",
}


def _load_german_model() -> object | None:
    global _nlp_de, _active_de_model_name
    if _nlp_de is not None:
        return _nlp_de
    with _model_lock:
        if _nlp_de is not None:
            return _nlp_de
        import spacy
        for model_name in _DE_MODEL_CASCADE:
            try:
                _nlp_de = spacy.load(model_name)
                _active_de_model_name = model_name
                logger.info(f"Loaded German spaCy model '{model_name}'")
                return _nlp_de
            except OSError:
                logger.info(f"German spaCy model '{model_name}' not installed — trying next")
        logger.warning("No German spaCy model found. Install with: python -m spacy download de_core_news_lg")
        return None


def is_german_ner_available() -> bool:
    try:
        return _load_german_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_de(text: str) -> bool:
    return _is_false_positive_person_generic(text, _DE_PERSON_STOPWORDS)


def _is_false_positive_org_de(text: str) -> bool:
    return _is_false_positive_org_generic(text, _DE_ORG_STOPWORDS, _GENERIC_STOPWORDS)


_DE_CONFIG = _LangNERConfig(
    label_map=_SPACY_DE_LABEL_MAP,
    article_prefixes=(
        "der ", "Der ", "die ", "Die ", "das ", "Das ",
        "den ", "Den ", "dem ", "Dem ", "des ", "Des ",
        "ein ", "Ein ", "eine ", "Eine ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_de,
    fp_org=_is_false_positive_org_de,
    generic_stopwords_filter=False,
    active_model_name=_get_active_de_model,
    org_context_prefixes=(
        "Gesellschaft ", "gesellschaft ", "Unternehmen ", "unternehmen ",
        "Firma ", "firma ",
    ),
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_de(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _DE_CONFIG)


def detect_ner_german(text: str) -> list[NERMatch]:
    """Run German spaCy NER on text."""
    if not _is_german_text(text):
        logger.info("Text does not appear to be German — skipping German NER")
        return []
    nlp = _load_german_model()
    if nlp is None:
        logger.info("No German spaCy model available — skipping German NER")
        return []
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_de(nlp, text, global_offset=0)
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        all_matches.extend(_process_chunk_de(nlp, chunk, global_offset=offset))
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break
    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# Spanish spaCy NER
# ---------------------------------------------------------------------------

_SPACY_ES_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
}

_ES_PERSON_STOPWORDS: set[str] = {
    "señor", "senor", "señora", "senora", "señorita", "senorita",
    "don", "doña", "dona",
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al",
    "él", "ella", "nosotros", "vosotros", "ellos", "ellas",
    "su", "sus", "mi", "mis", "tu", "tus",
    "este", "esta", "estos", "estas", "ese", "esa",
    "nuestro", "nuestra", "nuestros", "nuestras",
    "página", "pagina", "sección", "seccion", "tabla", "figura",
    "capítulo", "capitulo", "anexo",
    "total", "importe", "saldo", "fecha", "número", "numero", "tipo",
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo",
    # Financial terms
    "balance", "activo", "pasivo", "patrimonio",
    "ingreso", "ingresos", "gasto", "gastos",
    "beneficio", "pérdida", "perdida",
    "amortización", "amortizacion", "depreciación", "depreciacion",
    "provisión", "provision", "provisiones",
    "deuda", "deudas", "crédito", "credito",
    "capital", "impuesto", "impuestos",
    "dividendo", "dividendos", "interés", "interes",
}

_ES_ORG_STOPWORDS: set[str] = {
    "departamento", "sección", "seccion", "división", "division",
    "comité", "comite", "junta", "consejo", "comisión", "comision",
    "artículo", "articulo", "cláusula", "clausula", "anexo", "apéndice", "apendice",
    "tabla", "figura", "gráfico", "grafico", "cuadro",
    "ley", "decreto", "reglamento", "ordenanza", "estatuto",
    "contrato", "acuerdo", "convenio",
    "informe", "resumen", "memoria",
    # Financial terms
    "balance", "activo", "activos", "pasivo", "pasivos",
    "patrimonio", "capital",
    "ingresos", "gastos",
    "beneficio", "beneficios", "pérdida", "perdida", "pérdidas", "perdidas",
    "amortización", "amortizacion",
    "provisión", "provision", "provisiones",
    "ejercicio", "cierre", "consolidado",
    "cuenta", "cuentas", "partida", "partidas",
    "inversión", "inversion", "inversiones",
    "préstamo", "prestamo", "préstamos", "prestamos",
    "inventario", "existencias",
}


def _load_spanish_model() -> object | None:
    global _nlp_es, _active_es_model_name
    if _nlp_es is not None:
        return _nlp_es
    with _model_lock:
        if _nlp_es is not None:
            return _nlp_es
        import spacy
        for model_name in _ES_MODEL_CASCADE:
            try:
                _nlp_es = spacy.load(model_name)
                _active_es_model_name = model_name
                logger.info(f"Loaded Spanish spaCy model '{model_name}'")
                return _nlp_es
            except OSError:
                logger.info(f"Spanish spaCy model '{model_name}' not installed — trying next")
        logger.warning("No Spanish spaCy model found. Install with: python -m spacy download es_core_news_lg")
        return None


def is_spanish_ner_available() -> bool:
    try:
        return _load_spanish_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_es(text: str) -> bool:
    return _is_false_positive_person_generic(text, _ES_PERSON_STOPWORDS)


def _is_false_positive_org_es(text: str) -> bool:
    return _is_false_positive_org_generic(text, _ES_ORG_STOPWORDS, _GENERIC_STOPWORDS)


_ES_CONFIG = _LangNERConfig(
    label_map=_SPACY_ES_LABEL_MAP,
    article_prefixes=(
        "el ", "El ", "la ", "La ", "los ", "Los ", "las ", "Las ",
        "un ", "Un ", "una ", "Una ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_es,
    fp_org=_is_false_positive_org_es,
    generic_stopwords_filter=False,
    active_model_name=_get_active_es_model,
    org_context_prefixes=(
        "sociedad ",
    ),
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_es(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _ES_CONFIG)


def detect_ner_spanish(text: str) -> list[NERMatch]:
    """Run Spanish spaCy NER on text."""
    if not _is_spanish_text(text):
        logger.info("Text does not appear to be Spanish — skipping Spanish NER")
        return []
    nlp = _load_spanish_model()
    if nlp is None:
        logger.info("No Spanish spaCy model available — skipping Spanish NER")
        return []
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_es(nlp, text, global_offset=0)
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        all_matches.extend(_process_chunk_es(nlp, chunk, global_offset=offset))
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break
    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# Dutch spaCy NER
# ---------------------------------------------------------------------------

_SPACY_NL_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,       # nl models older versions
    "PERSON": PIIType.PERSON,    # nl models newer versions
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    "GPE": PIIType.LOCATION,
}

_NL_PERSON_STOPWORDS: set[str] = {
    "de", "het", "een",
    "meneer", "mevrouw", "mijnheer",
    "hij", "zij", "wij", "jullie", "hen", "haar",
    "zijn", "haar", "hun", "ons", "onze",
    "mijn", "jouw", "uw",
    "dit", "dat", "deze", "die",
    "pagina", "sectie", "tabel", "figuur", "hoofdstuk", "bijlage",
    "totaal", "bedrag", "saldo", "datum", "nummer", "type",
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
    "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag",
    # Financial terms
    "balans", "activa", "passiva", "vermogen",
    "winst", "verlies", "omzet",
    "afschrijving", "afschrijvingen",
    "voorziening", "voorzieningen",
    "schuld", "schulden", "vordering", "vorderingen",
    "kapitaal", "belasting", "belastingen",
    "dividend", "rente",
    "resultaat", "resultaten",
}

_NL_ORG_STOPWORDS: set[str] = {
    "afdeling", "sectie", "divisie",
    "commissie", "bestuur", "raad", "comité", "comite",
    "artikel", "clausule", "bijlage", "appendix",
    "tabel", "figuur", "grafiek", "diagram", "overzicht",
    "wet", "verordening", "statuut", "besluit", "reglement",
    "overeenkomst", "contract", "verdrag",
    "verslag", "samenvatting", "rapport",
    # Financial terms
    "balans", "activa", "passiva",
    "eigen", "vermogen", "vreemd",
    "winst", "verlies", "omzet",
    "afschrijving", "afschrijvingen",
    "voorziening", "voorzieningen",
    "jaarrekening", "boekjaar",
    "vordering", "vorderingen",
    "schuld", "schulden",
    "investering", "investeringen",
    "lening", "leningen",
    "voorraad", "voorraden",
}


def _load_dutch_model() -> object | None:
    global _nlp_nl, _active_nl_model_name
    if _nlp_nl is not None:
        return _nlp_nl
    with _model_lock:
        if _nlp_nl is not None:
            return _nlp_nl
        import spacy
        for model_name in _NL_MODEL_CASCADE:
            try:
                _nlp_nl = spacy.load(model_name)
                _active_nl_model_name = model_name
                logger.info(f"Loaded Dutch spaCy model '{model_name}'")
                return _nlp_nl
            except OSError:
                logger.info(f"Dutch spaCy model '{model_name}' not installed — trying next")
        logger.warning("No Dutch spaCy model found. Install with: python -m spacy download nl_core_news_lg")
        return None


def is_dutch_ner_available() -> bool:
    try:
        return _load_dutch_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_nl(text: str) -> bool:
    return _is_false_positive_person_generic(text, _NL_PERSON_STOPWORDS)


def _is_false_positive_org_nl(text: str) -> bool:
    return _is_false_positive_org_generic(text, _NL_ORG_STOPWORDS, _GENERIC_STOPWORDS)


_NL_CONFIG = _LangNERConfig(
    label_map=_SPACY_NL_LABEL_MAP,
    article_prefixes=(
        "de ", "De ", "het ", "Het ",
        "een ", "Een ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_nl,
    fp_org=_is_false_positive_org_nl,
    generic_stopwords_filter=False,
    active_model_name=_get_active_nl_model,
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_nl(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _NL_CONFIG)


def detect_ner_dutch(text: str) -> list[NERMatch]:
    """Run Dutch spaCy NER on text."""
    if not _is_dutch_text(text):
        logger.info("Text does not appear to be Dutch — skipping Dutch NER")
        return []
    nlp = _load_dutch_model()
    if nlp is None:
        logger.info("No Dutch spaCy model available — skipping Dutch NER")
        return []
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_nl(nlp, text, global_offset=0)
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        all_matches.extend(_process_chunk_nl(nlp, chunk, global_offset=offset))
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break
    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# Portuguese spaCy NER
# ---------------------------------------------------------------------------

_SPACY_PT_LABEL_MAP: dict[str, PIIType] = {
    "PER": PIIType.PERSON,       # pt models older versions
    "PERSON": PIIType.PERSON,    # pt models newer versions
    "ORG": PIIType.ORG,
    "LOC": PIIType.LOCATION,
    "GPE": PIIType.LOCATION,
}

_PT_PERSON_STOPWORDS: set[str] = {
    "o", "a", "os", "as",
    "senhor", "senhora", "sr", "sra", "dr", "dra",
    "ele", "ela", "eles", "elas", "nós", "vós",
    "seu", "sua", "seus", "suas",
    "meu", "minha", "meus", "minhas",
    "este", "esta", "estes", "estas",
    "isso", "isto", "aquilo",
    "página", "seção", "tabela", "figura", "capítulo", "anexo",
    "total", "valor", "saldo", "data", "número", "tipo",
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    "segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo",
    # Financial terms
    "balanço", "ativo", "passivo", "patrimônio",
    "lucro", "prejuízo", "receita",
    "depreciação", "amortização",
    "provisão", "provisões",
    "dívida", "crédito", "débito",
    "capital", "imposto", "impostos",
    "dividendo", "juro", "juros",
    "resultado", "resultados",
}

_PT_ORG_STOPWORDS: set[str] = {
    "departamento", "seção", "divisão",
    "comissão", "diretoria", "conselho", "comitê",
    "artigo", "cláusula", "anexo", "apêndice",
    "tabela", "figura", "gráfico", "diagrama", "resumo",
    "lei", "decreto", "estatuto", "regulamento",
    "acordo", "contrato", "tratado",
    "relatório", "sumário",
    # Financial terms
    "balanço", "ativo", "passivo",
    "patrimônio", "líquido",
    "lucro", "prejuízo", "receita",
    "depreciação", "amortização",
    "provisão", "provisões",
    "demonstração", "financeira",
    "exercício", "período",
    "crédito", "débito",
    "dívida", "dívidas",
    "investimento", "investimentos",
    "empréstimo", "empréstimos",
    "estoque", "estoques",
}


def _load_portuguese_model() -> object | None:
    global _nlp_pt, _active_pt_model_name
    if _nlp_pt is not None:
        return _nlp_pt
    with _model_lock:
        if _nlp_pt is not None:
            return _nlp_pt
        import spacy
        for model_name in _PT_MODEL_CASCADE:
            try:
                _nlp_pt = spacy.load(model_name)
                _active_pt_model_name = model_name
                logger.info(f"Loaded Portuguese spaCy model '{model_name}'")
                return _nlp_pt
            except OSError:
                logger.info(f"Portuguese spaCy model '{model_name}' not installed — trying next")
        logger.warning("No Portuguese spaCy model found. Install with: python -m spacy download pt_core_news_lg")
        return None


def is_portuguese_ner_available() -> bool:
    try:
        return _load_portuguese_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_pt(text: str) -> bool:
    return _is_false_positive_person_generic(text, _PT_PERSON_STOPWORDS)


def _is_false_positive_org_pt(text: str) -> bool:
    return _is_false_positive_org_generic(text, _PT_ORG_STOPWORDS, _GENERIC_STOPWORDS)


_PT_CONFIG = _LangNERConfig(
    label_map=_SPACY_PT_LABEL_MAP,
    article_prefixes=(
        "o ", "O ", "a ", "A ", "os ", "Os ", "as ", "As ",
        "um ", "Um ", "uma ", "Uma ",
    ),
    strip_title_suffixes=False,
    fp_person=_is_false_positive_person_pt,
    fp_org=_is_false_positive_org_pt,
    generic_stopwords_filter=False,
    active_model_name=_get_active_pt_model,
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.40, PIIType.LOCATION: 0.25,
    },
    person_multiword_cap=0.92,
    org_3word_cap=0.85,
    person_single_penalty=0.18,
    org_single_floor=0.30,
    model_boost_tiers=(("_lg", 0.05, 0.95), ("_md", 0.03, 0.92)),
)


def _process_chunk_pt(nlp, text: str, global_offset: int) -> list[NERMatch]:
    return _process_chunk_generic(nlp, text, global_offset, _PT_CONFIG)


def detect_ner_portuguese(text: str) -> list[NERMatch]:
    """Run Portuguese spaCy NER on text."""
    if not _is_portuguese_text(text):
        logger.info("Text does not appear to be Portuguese — skipping Portuguese NER")
        return []
    nlp = _load_portuguese_model()
    if nlp is None:
        logger.info("No Portuguese spaCy model available — skipping Portuguese NER")
        return []
    if len(text) <= _CHUNK_SIZE:
        return _process_chunk_pt(nlp, text, global_offset=0)
    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        all_matches.extend(_process_chunk_pt(nlp, chunk, global_offset=offset))
        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break
    return _deduplicate_matches(all_matches)


# ---------------------------------------------------------------------------
# NER language registry — unified dispatch for multilingual NER
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NERLanguageEntry:
    """Registry entry for a language-specific NER backend."""
    lang_code: str
    lang_label: str
    is_text: Callable[[str], bool]       # e.g. _is_french_text
    is_available: Callable[[], bool]     # e.g. is_french_ner_available
    detect: Callable[[str], list[NERMatch]]  # e.g. detect_ner_french


NER_LANGUAGE_REGISTRY: list[NERLanguageEntry] = [
    NERLanguageEntry("fr", "French", _is_french_text, is_french_ner_available, detect_ner_french),
    NERLanguageEntry("it", "Italian", _is_italian_text, is_italian_ner_available, detect_ner_italian),
    NERLanguageEntry("de", "German", _is_german_text, is_german_ner_available, detect_ner_german),
    NERLanguageEntry("es", "Spanish", _is_spanish_text, is_spanish_ner_available, detect_ner_spanish),
    NERLanguageEntry("nl", "Dutch", _is_dutch_text, is_dutch_ner_available, detect_ner_dutch),
    NERLanguageEntry("pt", "Portuguese", _is_portuguese_text, is_portuguese_ner_available, detect_ner_portuguese),
]


def detect_ner_multilingual(text: str) -> list[tuple[str, list[NERMatch]]]:
    """Run all applicable non-English NER models and return (lang_code, matches) pairs.

    Only runs models for languages detected in the text. Skips English text.
    """
    if _is_english_text(text):
        return []

    results: list[tuple[str, list[NERMatch]]] = []
    for entry in NER_LANGUAGE_REGISTRY:
        if entry.is_text(text) and entry.is_available():
            try:
                matches = entry.detect(text)
                if matches:
                    results.append((entry.lang_code, matches))
            except Exception as e:
                logger.error("%s NER detection failed: %s", entry.lang_label, e)
    return results


# ---------------------------------------------------------------------------
# Lightweight heuristic name detector (fallback when spaCy isn't available)
# ---------------------------------------------------------------------------

# Common first names (top ~150 English + ~80 multilingual first names)
# for heuristic matching.
# EXCLUDES names that are also common English words (Grace, Mark, Frank, etc.)
# to avoid false positives on document text.
_COMMON_FIRST_NAMES: set[str] = {
    # English
    "james", "john", "robert", "michael", "david", "william", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "donald", "steven", "paul", "andrew", "joshua",
    "kenneth", "kevin", "brian", "george", "timothy", "ronald", "edward",
    "jason", "jeffrey", "ryan", "jacob", "nicholas", "eric",
    "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
    "samuel", "raymond", "gregory", "patrick", "alexander",
    "dennis", "jerry", "tyler", "aaron", "jose", "nathan", "henry", "peter",
    "adam", "zachary", "walter", "kyle", "harold", "carl", "jeremy", "roger",
    "keith", "gerald", "eugene", "terry", "sean", "austin", "arthur", "jesse",
    "dylan", "bryan", "jordan", "bruce", "albert", "willie",
    "gabriel", "logan", "ralph", "lawrence", "wayne", "elijah", "randy",
    "vincent", "philip", "bobby", "johnny", "bradley",
    "mary", "patricia", "jennifer", "linda", "barbara", "elizabeth", "susan",
    "jessica", "sarah", "karen", "lisa", "nancy", "betty", "margaret", "sandra",
    "ashley", "dorothy", "kimberly", "emily", "donna", "michelle", "carol",
    "amanda", "melissa", "deborah", "stephanie", "rebecca", "sharon", "laura",
    "cynthia", "kathleen", "amy", "angela", "shirley", "anna", "brenda",
    "pamela", "emma", "nicole", "helen", "samantha", "katherine", "christine",
    "debra", "rachel", "carolyn", "janet", "catherine", "maria", "heather",
    "diane", "ruth", "julie", "olivia", "joyce", "virginia", "victoria",
    "kelly", "lauren", "christina", "joan", "evelyn", "judith", "megan",
    "andrea", "cheryl", "hannah", "jacqueline", "martha", "gloria", "teresa",
    "sara", "madison", "frances", "kathryn", "janice", "jean", "abigail",
    "alice", "judy", "sophia", "denise", "doris", "marilyn",
    "danielle", "beverly", "isabella", "theresa", "diana", "natalie", "brittany",
    "charlotte", "marie", "kayla", "alexis", "lori",
    # French
    "jean", "pierre", "jacques", "philippe", "michel", "alain", "nicolas",
    "françois", "francois", "henri", "louis", "laurent", "bernard",
    "marie", "sophie", "isabelle", "nathalie", "céline", "celine",
    "valérie", "valerie", "christine", "sylvie", "véronique", "veronique",
    "monique", "brigitte", "pascal", "thierry", "yves", "denis",
    # German
    "hans", "klaus", "wolfgang", "dieter", "jürgen", "jurgen",
    "karsten", "matthias", "stefan", "andreas", "markus", "bernd",
    "werner", "helmut", "gerhard", "rainer", "heinz", "ernst",
    "uwe", "manfred", "horst", "gerd", "ulrich", "franz",
    "sabine", "monika", "petra", "ursula", "karin", "renate",
    "ingrid", "helga", "christa", "gudrun", "elfriede",
    # Spanish
    "carlos", "miguel", "fernando", "rafael", "alejandro", "javier",
    "sergio", "jorge", "pablo", "ángel", "angel", "jesús", "jesus",
    "ramón", "ramon", "antonio", "roberto", "pedro", "alberto",
    "carmen", "marta", "pilar", "mercedes", "consuelo", "rosario",
    "dolores", "cristina", "elena", "beatriz", "lucía", "lucia",
    # Italian
    "giuseppe", "giovanni", "marco", "mario", "francesco", "antonio",
    "alessandro", "andrea", "stefano", "matteo", "lorenzo",
    "roberto", "paolo", "giorgio", "luca", "riccardo",
    "giulia", "francesca", "valentina", "chiara", "alessandra",
    "federica", "silvia", "eleonora", "claudia", "simona",
    # Dutch
    "johannes", "willem", "hendrik", "cornelis", "pieter",
    "gerrit", "jacobus", "theodorus",
    "johanna", "geertruida",
    # Portuguese
    "joão", "joao", "pedro", "fernando", "paulo", "rui",
    "ricardo", "tiago", "gonçalo", "goncalo", "nuno",
    "ana", "isabel", "beatriz", "mariana", "catarina",
}

# Patterns for the heuristic fallback — use literal space (not \s+) so
# we don't match across tab-separated columns or wide whitespace.
# Support accented capitals (À-Ü) for multilingual name matching.
_CAPITALIZED_NAME = re.compile(
    r"\b([A-ZÀ-Ü][a-zà-ü]{1,20}) ([A-ZÀ-Ü][a-zà-ü]{1,20}(?: [A-ZÀ-Ü][a-zà-ü]{1,20})?)\b"
)


def detect_names_heuristic(text: str) -> list[NERMatch]:
    """
    Lightweight heuristic name detection — used as a fallback when
    no spaCy or BERT model is available.

    Looks for sequences of 2-3 capitalized words where the first word
    is a known common first name. Works for all supported languages.
    """

    matches: list[NERMatch] = []

    for m in _CAPITALIZED_NAME.finditer(text):
        first_word = m.group(1).lower()
        if first_word not in _COMMON_FIRST_NAMES:
            continue

        full_match = m.group(0)

        # Trim at newline
        nl_idx = full_match.find("\n")
        if nl_idx > 0:
            full_match = full_match[:nl_idx].strip()
        if len(full_match.split()) < 2:
            continue

        # Skip if it looks like a title or header (all words capitalized
        # in a short line is suspicious)
        if _is_false_positive_person(full_match):
            continue

        # Skip if any word is in generic stopwords (catches "John Total" etc.)
        # or is a job title (catches "David Chairman" etc.)
        words = full_match.lower().split()
        if any(w in _GENERIC_STOPWORDS or w in _PERSON_STOPWORDS or w in _TITLE_SUFFIXES for w in words):
            continue

        word_count = len(full_match.split())
        # Low confidence so heuristic alone doesn't survive threshold;
        # it only shows if NER or regex also flags the same span (cross-layer boost).
        confidence = 0.50 if word_count == 2 else 0.55

        matches.append(NERMatch(
            start=m.start(),
            end=m.end(),
            text=full_match,
            pii_type=PIIType.PERSON,
            confidence=confidence,
        ))

    return _deduplicate_matches(matches)


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


def unload_models() -> None:
    """Free memory held by all loaded spaCy NER models."""
    global _nlp, _active_model_name
    global _nlp_fr, _active_fr_model_name
    global _nlp_it, _active_it_model_name
    global _nlp_de, _active_de_model_name
    global _nlp_es, _active_es_model_name
    global _nlp_nl, _active_nl_model_name
    global _nlp_pt, _active_pt_model_name
    with _model_lock:
        _nlp = None
        _active_model_name = ""
        _nlp_fr = None
        _active_fr_model_name = ""
        _nlp_it = None
        _active_it_model_name = ""
        _nlp_de = None
        _active_de_model_name = ""
        _nlp_es = None
        _active_es_model_name = ""
        _nlp_nl = None
        _active_nl_model_name = ""
        _nlp_pt = None
        _active_pt_model_name = ""
    logger.info("spaCy NER models unloaded")
