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
from typing import NamedTuple

from spacy.lang.en.stop_words import STOP_WORDS as _EN_STOP_WORDS
from spacy.lang.fr.stop_words import STOP_WORDS as _FR_STOP_WORDS
from spacy.lang.it.stop_words import STOP_WORDS as _IT_STOP_WORDS

from models.schemas import PIIType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight language detection — skip English NER on non-English text
# ---------------------------------------------------------------------------
# Uses spaCy's built-in stop word lists so we need zero extra dependencies.

_EN_STOP_LOWER: set[str] = {w.lower() for w in _EN_STOP_WORDS}
_FR_STOP_LOWER: set[str] = {w.lower() for w in _FR_STOP_WORDS}
_IT_STOP_LOWER: set[str] = {w.lower() for w in _IT_STOP_WORDS}
_LANG_SAMPLE_SIZE = 2000  # characters to sample for language check
_ENGLISH_STOPWORD_THRESHOLD = 0.15  # 15% — English text typically 25-40%
_FRENCH_STOPWORD_THRESHOLD = 0.12   # 12% — French text typically 20-35%
_ITALIAN_STOPWORD_THRESHOLD = 0.12  # 12% — Italian text typically 20-35%


def _is_english_text(text: str) -> bool:
    """Quick heuristic: is *text* likely English?

    Samples the first ~2 000 characters, tokenises by whitespace,
    and checks what fraction of tokens are English stop words.
    English prose normally has 25-40 % stop words; non-English text
    (French, German, etc.) usually falls well below 15 %.
    """
    sample = text[:_LANG_SAMPLE_SIZE]
    words = [w.lower().strip(".,;:!?()[]{}\"'") for w in sample.split()]
    words = [w for w in words if len(w) >= 2]  # drop 1-char tokens
    if len(words) < 20:
        # Too short to judge — assume English to avoid blocking real PII
        return True
    stop_count = sum(1 for w in words if w in _EN_STOP_LOWER)
    ratio = stop_count / len(words)
    logger.debug(
        "Language check: %d/%d words (%.1f%%) are English stop words",
        stop_count, len(words), ratio * 100,
    )
    return ratio >= _ENGLISH_STOPWORD_THRESHOLD


def _is_french_text(text: str) -> bool:
    """Quick heuristic: is *text* likely French?

    Same approach as ``_is_english_text`` but using French stop words.
    """
    sample = text[:_LANG_SAMPLE_SIZE]
    words = [w.lower().strip(".,;:!?()[]{}\"'") for w in sample.split()]
    words = [w for w in words if len(w) >= 2]
    if len(words) < 20:
        return False  # too short to judge
    stop_count = sum(1 for w in words if w in _FR_STOP_LOWER)
    ratio = stop_count / len(words)
    logger.debug(
        "French language check: %d/%d words (%.1f%%) are French stop words",
        stop_count, len(words), ratio * 100,
    )
    return ratio >= _FRENCH_STOPWORD_THRESHOLD


def _is_italian_text(text: str) -> bool:
    """Quick heuristic: is *text* likely Italian?

    Same approach as ``_is_english_text`` but using Italian stop words.
    """
    sample = text[:_LANG_SAMPLE_SIZE]
    words = [w.lower().strip(".,;:!?()[]{}\"'") for w in sample.split()]
    words = [w for w in words if len(w) >= 2]
    if len(words) < 20:
        return False  # too short to judge
    stop_count = sum(1 for w in words if w in _IT_STOP_LOWER)
    ratio = stop_count / len(words)
    logger.debug(
        "Italian language check: %d/%d words (%.1f%%) are Italian stop words",
        stop_count, len(words), ratio * 100,
    )
    return ratio >= _ITALIAN_STOPWORD_THRESHOLD


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
    except (Exception, SystemExit) as e:
        logger.error(f"Failed to load any spaCy model: {e}")
        raise RuntimeError(
            "No spaCy NER model available. Install one with: "
            "python -m spacy download en_core_web_lg"
        ) from e


def _load_french_model():
    """Lazy-load the best available French spaCy model.

    Tries fr_core_news_lg → fr_core_news_md → fr_core_news_sm.
    If none are installed, attempts to download fr_core_news_sm.
    Returns None if no French model can be loaded.
    """
    global _nlp_fr, _active_fr_model_name
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

    # Nothing installed — attempt to download fr_core_news_sm
    logger.warning("No French spaCy model found. Downloading fr_core_news_sm…")
    try:
        spacy.cli.download("fr_core_news_sm")
        _nlp_fr = spacy.load("fr_core_news_sm")
        _active_fr_model_name = "fr_core_news_sm"
        logger.info("Using fallback French model 'fr_core_news_sm'")
        return _nlp_fr
    except (Exception, SystemExit) as e:
        logger.warning(f"Failed to load any French spaCy model: {e}")
        return None


def is_french_ner_available() -> bool:
    """Check whether a French NER model can be loaded."""
    try:
        return _load_french_model() is not None
    except BaseException:
        return False


def _is_false_positive_person(text: str) -> bool:
    """Return True if a PERSON entity is likely a false positive."""
    clean = text.strip().lower()
    # Single-word match that's a common false positive
    if clean in _PERSON_STOPWORDS:
        return True
    # All-caps short strings (likely acronyms, not names)
    if text.isupper() and len(text) <= 5:
        return True
    # Starts with a digit (unlikely name)
    if text.strip() and text.strip()[0].isdigit():
        return True
    # Single word that doesn't look like a real name
    words = text.strip().split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    return False


def _is_false_positive_org(text: str) -> bool:
    """Return True if an ORG entity is likely a false positive."""
    clean = text.strip().lower()
    if clean in _ORG_STOPWORDS:
        return True
    if clean in _GENERIC_STOPWORDS:
        return True
    # Very short org names are almost always noise
    if len(clean) <= 2:
        return True
    # Single short all-caps word (abbreviations like "IT", "HR", "AI")
    if text.isupper() and len(text.strip()) <= 4:
        return True
    return False


def _process_chunk(nlp, text: str, global_offset: int) -> list[NERMatch]:
    """Run NER on a single text chunk, adjusting offsets to the global text."""
    doc = nlp(text)
    matches: list[NERMatch] = []

    for ent in doc.ents:
        pii_type = _SPACY_LABEL_MAP.get(ent.label_)
        if pii_type is None:
            continue

        # Trim entity text at the first newline — spaCy sometimes grabs
        # content that spills across lines.
        raw_text = ent.text
        nl_idx = raw_text.find("\n")
        if nl_idx > 0:
            raw_text = raw_text[:nl_idx]
        cleaned = raw_text.strip()

        # Strip leading articles / filler words
        for prefix in ("the ", "The ", "a ", "A ", "an ", "An "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        # For PERSON entities, trim trailing job titles
        # e.g. "Kathryn Ruemmler Chief" → "Kathryn Ruemmler"
        if pii_type == PIIType.PERSON:
            words = cleaned.split()
            while len(words) > 2 and words[-1].lower() in _TITLE_SUFFIXES:
                words.pop()
            cleaned = " ".join(words)

        min_len = _MIN_ENTITY_LENGTH.get(pii_type, 2)
        if len(cleaned) < min_len:
            continue

        # Filter obvious false positives per type
        if pii_type == PIIType.PERSON and _is_false_positive_person(cleaned):
            continue
        if pii_type == PIIType.ORG and _is_false_positive_org(cleaned):
            continue

        # Filter generic NER noise — all-uppercase short tokens,
        # single-char entities, or purely-numeric strings.
        if cleaned.isupper() and len(cleaned) <= 5:
            continue
        if cleaned.isdigit():
            continue
        if cleaned.lower() in _GENERIC_STOPWORDS:
            continue

        end_char = ent.start_char + len(raw_text.rstrip())
        confidence = _estimate_confidence(ent, pii_type)
        matches.append(NERMatch(
            start=global_offset + ent.start_char,
            end=global_offset + end_char,
            text=cleaned,
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
}

_FR_ORG_STOPWORDS: set[str] = {
    "département", "departement", "service", "bureau", "direction",
    "section", "division", "commission", "comité", "comite",
    "article", "clause", "alinéa", "alinea", "annexe",
    "tableau", "figure", "graphique",
    "loi", "décret", "decret", "arrêté", "arrete", "règlement", "reglement",
    "contrat", "accord", "convention", "rapport", "résumé", "resume",
}


def _is_false_positive_person_fr(text: str) -> bool:
    """Return True if a French PERSON entity is likely a false positive."""
    clean = text.strip().lower()
    if clean in _FR_PERSON_STOPWORDS:
        return True
    if text.isupper() and len(text) <= 5:
        return True
    if text.strip() and text.strip()[0].isdigit():
        return True
    words = text.strip().split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    return False


def _is_false_positive_org_fr(text: str) -> bool:
    """Return True if a French ORG entity is likely a false positive."""
    clean = text.strip().lower()
    if clean in _FR_ORG_STOPWORDS:
        return True
    if clean in _GENERIC_STOPWORDS:
        return True
    if len(clean) <= 2:
        return True
    if text.isupper() and len(text.strip()) <= 4:
        return True
    return False


def _process_chunk_fr(nlp, text: str, global_offset: int) -> list[NERMatch]:
    """Run French NER on a single text chunk, adjusting offsets."""
    doc = nlp(text)
    matches: list[NERMatch] = []

    for ent in doc.ents:
        pii_type = _SPACY_FR_LABEL_MAP.get(ent.label_)
        if pii_type is None:
            continue

        raw_text = ent.text
        nl_idx = raw_text.find("\n")
        if nl_idx > 0:
            raw_text = raw_text[:nl_idx]
        cleaned = raw_text.strip()

        # Strip leading French articles
        for prefix in ("le ", "Le ", "la ", "La ", "l'", "L'",
                       "les ", "Les ", "un ", "Un ", "une ", "Une "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        min_len = _MIN_ENTITY_LENGTH.get(pii_type, 2)
        if len(cleaned) < min_len:
            continue

        if pii_type == PIIType.PERSON and _is_false_positive_person_fr(cleaned):
            continue
        if pii_type == PIIType.ORG and _is_false_positive_org_fr(cleaned):
            continue
        if cleaned.isupper() and len(cleaned) <= 5:
            continue
        if cleaned.isdigit():
            continue

        end_char = ent.start_char + len(raw_text.rstrip())
        confidence = _estimate_confidence_fr(ent, pii_type)
        matches.append(NERMatch(
            start=global_offset + ent.start_char,
            end=global_offset + end_char,
            text=cleaned,
            pii_type=pii_type,
            confidence=confidence,
        ))

    return matches


def _estimate_confidence_fr(ent, pii_type: PIIType) -> float:
    """Estimate confidence for a French spaCy entity."""
    base_confidence = {
        PIIType.PERSON: 0.78,
        PIIType.ORG: 0.55,
        PIIType.LOCATION: 0.40,
    }
    conf = base_confidence.get(pii_type, 0.40)

    text = ent.text.strip()
    word_count = len(text.split())

    if word_count >= 2 and pii_type == PIIType.PERSON:
        conf = min(conf + 0.08, 0.92)
    if word_count >= 2 and pii_type == PIIType.ORG:
        conf = min(conf + 0.15, 0.80)
    if word_count >= 3 and pii_type == PIIType.ORG:
        conf = min(conf + 0.05, 0.85)

    # Single-word entities — reduce confidence
    if pii_type == PIIType.PERSON and word_count == 1:
        conf = max(conf - 0.18, 0.40)
    if pii_type == PIIType.ORG and word_count == 1:
        conf = max(conf - 0.15, 0.30)
    if pii_type == PIIType.LOCATION and word_count == 1:
        conf = max(conf - 0.10, 0.30)

    # Boost for larger French models
    if _active_fr_model_name.endswith("_lg"):
        conf = min(conf + 0.05, 0.95)
    elif _active_fr_model_name.endswith("_md"):
        conf = min(conf + 0.03, 0.92)

    return round(conf, 4)


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


def _load_italian_model():
    """Lazy-load the best available Italian spaCy model.

    Tries it_core_news_lg → it_core_news_md → it_core_news_sm.
    If none are installed, attempts to download it_core_news_sm.
    Returns None if no Italian model can be loaded.
    """
    global _nlp_it, _active_it_model_name
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

    # Nothing installed — attempt to download it_core_news_sm
    logger.warning("No Italian spaCy model found. Downloading it_core_news_sm…")
    try:
        spacy.cli.download("it_core_news_sm")
        _nlp_it = spacy.load("it_core_news_sm")
        _active_it_model_name = "it_core_news_sm"
        logger.info("Using fallback Italian model 'it_core_news_sm'")
        return _nlp_it
    except (Exception, SystemExit) as e:
        logger.warning(f"Failed to load any Italian spaCy model: {e}")
        return None


def is_italian_ner_available() -> bool:
    """Check whether an Italian NER model can be loaded."""
    try:
        return _load_italian_model() is not None
    except BaseException:
        return False


def _is_false_positive_person_it(text: str) -> bool:
    """Return True if an Italian PERSON entity is likely a false positive."""
    clean = text.strip().lower()
    if clean in _IT_PERSON_STOPWORDS:
        return True
    if text.isupper() and len(text) <= 5:
        return True
    if text.strip() and text.strip()[0].isdigit():
        return True
    words = text.strip().split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    return False


def _is_false_positive_org_it(text: str) -> bool:
    """Return True if an Italian ORG entity is likely a false positive."""
    clean = text.strip().lower()
    if clean in _IT_ORG_STOPWORDS:
        return True
    if clean in _GENERIC_STOPWORDS:
        return True
    if len(clean) <= 2:
        return True
    if text.isupper() and len(text.strip()) <= 4:
        return True
    return False


def _process_chunk_it(nlp, text: str, global_offset: int) -> list[NERMatch]:
    """Run Italian NER on a single text chunk, adjusting offsets."""
    doc = nlp(text)
    matches: list[NERMatch] = []

    for ent in doc.ents:
        pii_type = _SPACY_IT_LABEL_MAP.get(ent.label_)
        if pii_type is None:
            continue

        raw_text = ent.text
        nl_idx = raw_text.find("\n")
        if nl_idx > 0:
            raw_text = raw_text[:nl_idx]
        cleaned = raw_text.strip()

        # Strip leading Italian articles
        for prefix in ("il ", "Il ", "lo ", "Lo ", "la ", "La ", "l'", "L'",
                       "le ", "Le ", "gli ", "Gli ", "i ", "I ",
                       "un ", "Un ", "uno ", "Uno ", "una ", "Una "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        min_len = _MIN_ENTITY_LENGTH.get(pii_type, 2)
        if len(cleaned) < min_len:
            continue

        if pii_type == PIIType.PERSON and _is_false_positive_person_it(cleaned):
            continue
        if pii_type == PIIType.ORG and _is_false_positive_org_it(cleaned):
            continue
        if cleaned.isupper() and len(cleaned) <= 5:
            continue
        if cleaned.isdigit():
            continue

        end_char = ent.start_char + len(raw_text.rstrip())
        confidence = _estimate_confidence_it(ent, pii_type)
        matches.append(NERMatch(
            start=global_offset + ent.start_char,
            end=global_offset + end_char,
            text=cleaned,
            pii_type=pii_type,
            confidence=confidence,
        ))

    return matches


def _estimate_confidence_it(ent, pii_type: PIIType) -> float:
    """Estimate confidence for an Italian spaCy entity."""
    base_confidence = {
        PIIType.PERSON: 0.78,
        PIIType.ORG: 0.55,
        PIIType.LOCATION: 0.40,
    }
    conf = base_confidence.get(pii_type, 0.40)

    text = ent.text.strip()
    word_count = len(text.split())

    if word_count >= 2 and pii_type == PIIType.PERSON:
        conf = min(conf + 0.08, 0.92)
    if word_count >= 2 and pii_type == PIIType.ORG:
        conf = min(conf + 0.15, 0.80)
    if word_count >= 3 and pii_type == PIIType.ORG:
        conf = min(conf + 0.05, 0.85)

    # Single-word entities — reduce confidence
    if pii_type == PIIType.PERSON and word_count == 1:
        conf = max(conf - 0.18, 0.40)
    if pii_type == PIIType.ORG and word_count == 1:
        conf = max(conf - 0.15, 0.30)
    if pii_type == PIIType.LOCATION and word_count == 1:
        conf = max(conf - 0.10, 0.30)

    # Boost for larger Italian models
    if _active_it_model_name.endswith("_lg"):
        conf = min(conf + 0.05, 0.95)
    elif _active_it_model_name.endswith("_md"):
        conf = min(conf + 0.03, 0.92)

    return round(conf, 4)


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


def _estimate_confidence(ent, pii_type: PIIType) -> float:
    """Estimate confidence for a spaCy entity based on heuristics."""
    base_confidence = {
        PIIType.PERSON: 0.80,
        PIIType.ORG: 0.45,
        PIIType.LOCATION: 0.40,   # generic place names are rarely PII
        PIIType.ADDRESS: 0.55,
    }
    conf = base_confidence.get(pii_type, 0.40)

    # Boost for multi-word entities (more likely correct, especially names)
    text = ent.text.strip()
    word_count = len(text.split())
    if word_count >= 2 and pii_type == PIIType.PERSON:
        conf = min(conf + 0.08, 0.95)   # "John Smith" > "John"
    # Multi-word ORGs are more likely real company names
    if word_count >= 2 and pii_type == PIIType.ORG:
        conf = min(conf + 0.15, 0.80)   # "Goldman Sachs" > "Company"
    if word_count >= 3 and pii_type == PIIType.ORG:
        conf = min(conf + 0.05, 0.80)

    # Single-word PERSON — reduce more aggressively (high FP rate)
    if pii_type == PIIType.PERSON and word_count == 1:
        conf = max(conf - 0.20, 0.40)

    # Single-word ORG — very likely a false positive
    if pii_type == PIIType.ORG and word_count == 1:
        conf = max(conf - 0.15, 0.25)

    # Single-word LOCATION — very likely noise ("London", "Tokyo")
    if pii_type == PIIType.LOCATION and word_count == 1:
        conf = max(conf - 0.10, 0.30)

    # Boost when using the transformer model (higher accuracy)
    if _active_model_name.endswith("_trf"):
        conf = min(conf + 0.08, 0.98)
    elif _active_model_name.endswith("_lg"):
        conf = min(conf + 0.03, 0.95)

    return round(conf, 4)


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
    except BaseException:
        return False
