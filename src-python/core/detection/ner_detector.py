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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words — lazy-loaded to avoid ~200-400ms import cost at module level
# ---------------------------------------------------------------------------

_EN_STOP_WORDS: set[str] | None = None
_FR_STOP_WORDS: set[str] | None = None
_IT_STOP_WORDS: set[str] | None = None


def _get_en_stop_words() -> set[str]:
    global _EN_STOP_WORDS
    if _EN_STOP_WORDS is None:
        from spacy.lang.en.stop_words import STOP_WORDS
        _EN_STOP_WORDS = STOP_WORDS
    return _EN_STOP_WORDS


def _get_fr_stop_words() -> set[str]:
    global _FR_STOP_WORDS
    if _FR_STOP_WORDS is None:
        from spacy.lang.fr.stop_words import STOP_WORDS
        _FR_STOP_WORDS = STOP_WORDS
    return _FR_STOP_WORDS


def _get_it_stop_words() -> set[str]:
    global _IT_STOP_WORDS
    if _IT_STOP_WORDS is None:
        from spacy.lang.it.stop_words import STOP_WORDS
        _IT_STOP_WORDS = STOP_WORDS
    return _IT_STOP_WORDS

# ---------------------------------------------------------------------------
# Lightweight language detection — skip English NER on non-English text
# ---------------------------------------------------------------------------
# Uses spaCy's built-in stop word lists so we need zero extra dependencies.
# Lazy-loaded to avoid ~200-400ms module-level import cost.

_EN_STOP_LOWER: set[str] | None = None
_FR_STOP_LOWER: set[str] | None = None
_IT_STOP_LOWER: set[str] | None = None


def _get_en_stop_lower() -> set[str]:
    global _EN_STOP_LOWER
    if _EN_STOP_LOWER is None:
        _EN_STOP_LOWER = {w.lower() for w in _get_en_stop_words()}
    return _EN_STOP_LOWER


def _get_fr_stop_lower() -> set[str]:
    global _FR_STOP_LOWER
    if _FR_STOP_LOWER is None:
        _FR_STOP_LOWER = {w.lower() for w in _get_fr_stop_words()}
    return _FR_STOP_LOWER


def _get_it_stop_lower() -> set[str]:
    global _IT_STOP_LOWER
    if _IT_STOP_LOWER is None:
        _IT_STOP_LOWER = {w.lower() for w in _get_it_stop_words()}
    return _IT_STOP_LOWER


_LANG_SAMPLE_SIZE = 2000  # characters to sample for language check
_ENGLISH_STOPWORD_THRESHOLD = 0.15  # 15% — English text typically 25-40%
_FRENCH_STOPWORD_THRESHOLD = 0.12   # 12% — French text typically 20-35%
_ITALIAN_STOPWORD_THRESHOLD = 0.12  # 12% — Italian text typically 20-35%


def _is_language(
    text: str,
    stopwords: set[str],
    threshold: float,
    lang_label: str,
    short_default: bool = False,
) -> bool:
    """Unified language-detection heuristic (M7: dedup EN/FR/IT).

    Samples the first ~2 000 characters, tokenises by whitespace,
    and checks what fraction of tokens are in the given *stopwords* set.
    *short_default* is returned when the sample is too short to judge
    (True for English so we don't block PII, False for others).
    """
    sample = text[:_LANG_SAMPLE_SIZE]
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


def _is_english_text(text: str) -> bool:
    return _is_language(text, _get_en_stop_lower(), _ENGLISH_STOPWORD_THRESHOLD, "English", short_default=True)


def _is_french_text(text: str) -> bool:
    return _is_language(text, _get_fr_stop_lower(), _FRENCH_STOPWORD_THRESHOLD, "French")


def _is_italian_text(text: str) -> bool:
    return _is_language(text, _get_it_stop_lower(), _ITALIAN_STOPWORD_THRESHOLD, "Italian")


class NERMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# Map spaCy entity labels to our PII types.
# Only keep types that are genuinely PII — drop NORP (nationalities),
# FAC (facilities), MONEY (amounts), and DATE (handled better by regex).
_SPACY_LABEL_MAP: dict[str, PIIType] = {
    "PERSON": PIIType.PERSON,
    "ORG": PIIType.ORG,
    "GPE": PIIType.LOCATION,      # Countries, cities, states
    "LOC": PIIType.LOCATION,      # Non-GPE locations
    # DATE intentionally omitted — regex handles concrete dates much better;
    # NER dates are mostly noise ("Q4 2024", "the Year Ended ...", "Tuesday").
}

# Minimum entity text length per type (filter out noise)
_MIN_ENTITY_LENGTH: dict[PIIType, int] = {
    PIIType.PERSON: 3,
    PIIType.ORG: 2,
    PIIType.LOCATION: 2,
    PIIType.DATE: 4,
    PIIType.ADDRESS: 3,
    PIIType.UNKNOWN: 3,
}

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

# Lock protecting lazy model initialisation (all three languages)
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

@dataclass(frozen=True)
class _LangNERConfig:
    """All per-language parameters that differ between EN/FR/IT NER."""

    label_map: dict[str, PIIType]
    article_prefixes: tuple[str, ...]
    strip_title_suffixes: bool  # True only for EN
    fp_person: Callable[[str], bool]
    fp_org: Callable[[str], bool]
    generic_stopwords_filter: bool  # extra _GENERIC_STOPWORDS check (EN only)
    active_model_name: Callable[[], str]
    # confidence tuning
    base_confidence: dict[PIIType, float] = field(default_factory=dict)
    person_multiword_cap: float = 0.95
    org_3word_cap: float = 0.80
    person_single_penalty: float = 0.20
    org_single_floor: float = 0.25
    model_boost_tiers: tuple[tuple[str, float, float], ...] = ()


def _get_active_en_model() -> str:
    return _active_model_name


def _get_active_fr_model() -> str:
    return _active_fr_model_name


def _get_active_it_model() -> str:
    return _active_it_model_name


_EN_CONFIG = _LangNERConfig(
    label_map=_SPACY_LABEL_MAP,
    article_prefixes=("the ", "The ", "a ", "A ", "an ", "An "),
    strip_title_suffixes=True,
    fp_person=_is_false_positive_person,
    fp_org=_is_false_positive_org,
    generic_stopwords_filter=True,
    active_model_name=_get_active_en_model,
    base_confidence={
        PIIType.PERSON: 0.80, PIIType.ORG: 0.30,
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

        end_char = ent.start_char + len(raw_text.rstrip())
        confidence = _estimate_confidence_generic(ent, pii_type, cfg)
        matches.append(NERMatch(
            start=global_offset + ent.start_char,
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
    "elles", "ils", "elle", "il",  # pronouns sometimes tagged as ORG
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
    return _is_false_positive_person_generic(text, _FR_PERSON_STOPWORDS)


def _is_false_positive_org_fr(text: str) -> bool:
    """Return True if a French ORG entity is likely a false positive."""
    return _is_false_positive_org_generic(text, _FR_ORG_STOPWORDS, _GENERIC_STOPWORDS)


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
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.35, PIIType.LOCATION: 0.25,
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
        return _process_chunk_fr(nlp, text[:1_000_000], global_offset=0)

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
    base_confidence={
        PIIType.PERSON: 0.78, PIIType.ORG: 0.35, PIIType.LOCATION: 0.25,
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
        return _process_chunk_it(nlp, text[:1_000_000], global_offset=0)

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
# Lightweight heuristic name detector (fallback when spaCy isn't available)
# ---------------------------------------------------------------------------

# Common first names (top ~150 English first names) for heuristic matching.
# EXCLUDES names that are also common English words (Grace, Mark, Frank, etc.)
# to avoid false positives on document text.
_COMMON_FIRST_NAMES: set[str] = {
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
}

# Patterns for the heuristic fallback — use literal space (not \s+) so
# we don't match across tab-separated columns or wide whitespace.
_CAPITALIZED_NAME = re.compile(
    r"\b([A-Z][a-z]{1,20}) ([A-Z][a-z]{1,20}(?: [A-Z][a-z]{1,20})?)\b"
)


def detect_names_heuristic(text: str) -> list[NERMatch]:
    """
    Lightweight heuristic name detection — used as a fallback when
    no spaCy or BERT model is available.

    Looks for sequences of 2-3 capitalized words where the first word
    is a known common first name. Confidence is moderate (0.65-0.75).

    Also skipped for non-English text (the first-name list is English).
    """
    if not _is_english_text(text):
        logger.info("Text does not appear to be English — skipping heuristic name detection")
        return []

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
    global _nlp, _active_model_name, _nlp_fr, _active_fr_model_name, _nlp_it, _active_it_model_name
    with _model_lock:
        _nlp = None
        _active_model_name = ""
        _nlp_fr = None
        _active_fr_model_name = ""
        _nlp_it = None
        _active_it_model_name = ""
    logger.info("spaCy NER models unloaded")
