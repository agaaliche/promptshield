"""Pipeline-level noise filtering using language dictionaries and pattern rules.

Centralises all noise filtering logic so that pipeline, merge, and
propagation modules share a single definition.

ORG noise filtering uses comprehensive language dictionaries (~30k words each)
for all 7 supported languages (EN, FR, DE, ES, IT, NL, PT).  A candidate ORG
match is filtered when all its words are common dictionary words and it lacks
a legal company suffix.

LOCATION and PERSON noise filtering uses domain-specific curated sets
(building/facility terms, financial terms) because proper nouns (city names,
person names) naturally appear in language dictionaries and must not be
filtered.
"""

from __future__ import annotations

import re as _re
import unicodedata as _unicodedata

import Stemmer as _Stemmer  # PyStemmer — Snowball stemmers

from core.detection import detection_config as det_cfg
from pathlib import Path
from typing import Set

from core.text_utils import remove_accents as _remove_accents
from models.schemas import PIIType

# ---------------------------------------------------------------------------
# Snowball stemmers — lazy-initialized per language
# ---------------------------------------------------------------------------

# Mapping from ISO 639-1 codes to Snowball language names
_SNOWBALL_LANG_MAP: dict[str, str] = {
    "en": "english",
    "fr": "french",
    "de": "german",
    "es": "spanish",
    "it": "italian",
    "nl": "dutch",
    "pt": "portuguese",
}

_stemmers: dict[str, _Stemmer.Stemmer] = {}


def _get_stemmer(lang: str) -> _Stemmer.Stemmer | None:
    """Get or create a Snowball stemmer for the given language code."""
    if lang in _stemmers:
        return _stemmers[lang]
    snowball_name = _SNOWBALL_LANG_MAP.get(lang)
    if not snowball_name:
        return None
    stemmer = _Stemmer.Stemmer(snowball_name)
    _stemmers[lang] = stemmer
    return stemmer


def _stem_word(word: str, langs: tuple[str, ...] = ("en", "fr", "de", "es", "it", "nl", "pt")) -> set[str]:
    """Return the set of possible stems for a word across given languages.
    
    Returns stems from all requested languages since we don't always know
    the document language when filtering noise.
    """
    stems: set[str] = set()
    for lang in langs:
        stemmer = _get_stemmer(lang)
        if stemmer:
            stems.add(stemmer.stemWord(word))
    return stems


# ---------------------------------------------------------------------------
# Legal-suffix regex — shared across all noise filters
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_RE: _re.Pattern[str] = _re.compile(
    r'\b(?:inc|incorporated|corp|corporation|ltd|limited|llc|llp|plc|co|company|lp|'
    r'sas|sarl|gmbh|ag|bv|nv|'
    r'kg|kgaa|ohg|ug|mbh|e\.?k\.?|e\.?v\.?|se|'
    r'aktiengesellschaft|kommanditgesellschaft|'  # DE long forms
    r'lt[ée]e|limit[ée]e|enr|s\.?e\.?n\.?c\.?|'
    r'n\.\s*v\.?|b\.\s*v\.?|'  # NL: N.V., B.V.
    r's\.?a\.?r?\.?l?\.?|s\.?p\.?a\.?|s\.?r\.?l\.?)\b\.?',
    _re.IGNORECASE,
)


def _fix_double_utf8(text: str) -> str:
    """Fix double-encoded UTF-8 (mojibake) in text.
    
    When UTF-8 bytes are mistakenly decoded as Latin-1 and then re-encoded
    as UTF-8, common French/German characters become unreadable:
    - é → Ã© (C3 A9 → C3 83 C2 A9)
    - È → Ãˆ (C3 88 → C3 83 C2 88)
    
    This function detects and reverses that double-encoding.
    """
    try:
        # Try to fix by encoding to Latin-1 and decoding as UTF-8
        # This reverses the double-encoding
        fixed = text.encode('latin-1').decode('utf-8')
        # Only use the fixed version if it's actually different and valid
        if fixed != text:
            return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return text


# Character mapping for PDF encoding issues (wrong chars used in place of accents)
# Include both upper and lowercase versions since .lower() may have been called
_PDF_CHAR_MAP = str.maketrans({
    '\u00da': '\u00e9',  # Ú (218) → é (233)
    '\u00fa': '\u00e9',  # ú (250) → é (233) - lowercase version
    '\u00de': '\u00e8',  # Þ (222) → è (232)
    '\u00fe': '\u00e8',  # þ (254) → è (232) - lowercase version
    '\u00d4': '\u00f4',  # Ô (212) → ô (244)
    '\u00f4': '\u00f4',  # ô stays ô
    '\u0152': '\u0153',  # Œ → œ
})


def _fix_pdf_encoding(text: str) -> str:
    """Fix common PDF character encoding issues."""
    return text.translate(_PDF_CHAR_MAP)


def has_legal_suffix(text: str) -> bool:
    """Return True if *text* contains a legal company suffix anywhere."""
    return bool(LEGAL_SUFFIX_RE.search(text.strip()))


# ---------------------------------------------------------------------------
# Language dictionaries — lazy-loaded on first use to avoid startup cost
# ---------------------------------------------------------------------------

_DICT_DIR = Path(__file__).parent / "dictionaries"
_SUPPORTED_LANGS = ("en", "fr", "de", "es", "it", "nl", "pt")

# Sentinel used to detect uninitialized state
_UNLOADED: frozenset[str] = frozenset({"__UNLOADED__"})


def _load_dictionaries() -> frozenset[str]:
    """Load per-language dictionary files into a single lowercase word set."""
    words: set[str] = set()
    for lang in _SUPPORTED_LANGS:
        dict_path = _DICT_DIR / f"{lang}.txt"
        if dict_path.exists():
            with open(dict_path, encoding="utf-8") as f:
                words.update(line.strip() for line in f if line.strip())
    return frozenset(words)


def _load_single_dict(lang: str) -> frozenset[str]:
    """Load a single language dictionary file."""
    path = _DICT_DIR / f"{lang}.txt"
    if not path.exists():
        return frozenset()
    with open(path, encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if line.strip())


# Lazy-loaded: initialised to sentinel, populated on first access
_common_words: frozenset[str] = _UNLOADED
_german_words: frozenset[str] = _UNLOADED


def _get_common_words() -> frozenset[str]:
    """Return the combined dictionary word set, loading on first call."""
    global _common_words
    if _common_words is _UNLOADED:
        _common_words = _load_dictionaries()
    return _common_words


def _get_german_words() -> frozenset[str]:
    """Return the German dictionary word set, loading on first call."""
    global _german_words
    if _german_words is _UNLOADED:
        _german_words = _load_single_dict("de")
    return _german_words


# ── ORG noise (dictionary-based) ─────────────────────────────────────────
# No hand-curated word list — uses _common_words from language dictionaries.
# A candidate is noise if all its words are ordinary dictionary words and
# it doesn't carry a legal company suffix.

# Leading-article regex shared by all three noise functions
_ARTICLE_PREFIX_RE = _re.compile(
    r"^(?:[LlDd]['\u2019]\s*"  # FR: l', d'
    r"|[Ll][eao]s?\s+|[Dd][eiu]s?\s+|[Uu]n[ea]?\s+"  # FR
    r"|[Ee]l\s+|[Ll]os\s+|[Ll]as\s+"  # ES
    r"|[Ii]l\s+|[Gg]li\s+|[Uu]n[oa]?\s+"  # IT
    r"|[Dd](?:er|ie|as|en|em|es)\s+|[Ee]in[e]?\s+"  # DE
    r"|[Hh]et\s+|[Dd]e\s+|[Ee]en\s+"  # NL
    r"|[Oo]s?\s+|[Aa]s?\s+"  # PT
    r")"
)


def _is_org_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy ORG false-positive.

    Uses language dictionaries for vocabulary checks rather than a
    hand-curated word list.
    """
    _get_common_words()  # ensure dictionary is loaded into module global
    clean = text.strip()
    # Fix double-encoded UTF-8 (mojibake) for dictionary lookup
    clean_fixed = _fix_double_utf8(clean)
    low = clean.lower()
    low_fixed = clean_fixed.lower()
    
    def _in_dict_simple(w: str) -> bool:
        """Check if single word is in dictionary, with accent normalization and stemming."""
        # Strip trailing/leading punctuation (e.g., "pertinentes." -> "pertinentes")
        w = w.strip('.,;:!?()[]{}"\'\u2018\u2019\u201c\u201d')
        if not w:
            return True  # Empty after stripping = just punctuation, not a real word
        
        if w in _common_words:
            return True
        # Try mojibake fix
        w_fixed = _fix_double_utf8(w).lower()
        if w_fixed != w and w_fixed in _common_words:
            return True
        # Try PDF encoding fix (Ú→é, Þ→è)
        w_pdf_fixed = _fix_pdf_encoding(w).lower()
        if w_pdf_fixed != w and w_pdf_fixed in _common_words:
            return True
        # Try with accents removed (e.g., 'exhaustivite' matches 'exhaustivité')
        w_noaccent = _remove_accents(w)
        if w_noaccent != w and w_noaccent in _common_words:
            return True
        # Try adding accents — covers FR, ES, IT, PT, DE diacritics
        _ACCENT_SWAPS = [
            # French
            ('é', 'e'), ('è', 'e'), ('ê', 'e'), ('ë', 'e'),
            ('à', 'a'), ('â', 'a'),
            ('ô', 'o'), ('î', 'i'), ('û', 'u'), ('ù', 'u'),
            ('ç', 'c'),
            # Spanish
            ('á', 'a'), ('í', 'i'), ('ó', 'o'), ('ú', 'u'), ('ñ', 'n'),
            # Portuguese
            ('ã', 'a'), ('õ', 'o'),
            # German
            ('ä', 'a'), ('ö', 'o'), ('ü', 'u'), ('ß', 'ss'),
        ]
        for accented, plain in _ACCENT_SWAPS:
            if plain == 'ss':
                # ß→ss: try replacing 'ss' with 'ß'
                if 'ss' in w:
                    w_accented = w.replace('ss', 'ß', 1)
                    if w_accented in _common_words:
                        return True
            elif w.endswith(plain):
                w_accented = w[:-len(plain)] + accented
                if w_accented in _common_words:
                    return True

        # Use Snowball stemmers to find stems and check dictionary.
        # This replaces ~130 lines of hand-written suffix rules with linguistically
        # correct stemming for all 7 supported languages.
        for stem in _stem_word(w):
            if stem in _common_words:
                return True
            # Also try accent normalization on the stem
            stem_noaccent = _remove_accents(stem)
            if stem_noaccent != stem and stem_noaccent in _common_words:
                return True

        # German compound word decompounding (inline, up to 3 parts)
        # Use the German-only dictionary to avoid false positives from
        # cross-language coincidences (e.g. "gaspésiens" ≠ "gaspé"+"siens").
        _de_words = _get_german_words()
        if len(w) >= 8:
            for i in range(4, len(w) - 3):
                left = w[:i]
                if left not in _de_words:
                    continue
                right = w[i:]
                if right in _de_words:
                    return True
                # Try Fugen-element then direct match or recursive 2nd split
                _fuge_candidates = [('', right)]  # no Fuge
                for fg in ('s', 'es', 'n', 'en', 'e', 'er'):
                    if right.startswith(fg) and len(right) > len(fg) + 3:
                        _fuge_candidates.append((fg, right[len(fg):]))
                for _fg, remainder in _fuge_candidates:
                    if remainder in _de_words:
                        return True
                    # Try one more split (3-part compounds)
                    if len(remainder) >= 7:
                        for j in range(4, len(remainder) - 3):
                            left2 = remainder[:j]
                            if left2 not in _de_words:
                                continue
                            right2 = remainder[j:]
                            if right2 in _de_words:
                                return True
                            for fg2 in ('s', 'es', 'n', 'en', 'e', 'er'):
                                if right2.startswith(fg2) and len(right2) > len(fg2) + 3:
                                    rest2 = right2[len(fg2):]
                                    if rest2 in _de_words:
                                        return True

        return False
    
    def _in_dict(word: str) -> bool:
        """Check if word is in dictionary, trying both original and fixed encoding.
        
        Also handles:
        - Hyphenated compounds: 'sous-jacentes' -> 'sous' AND 'jacentes'
        - French contractions: "l'exhaustivité" -> just check 'exhaustivité'
        """
        w = word.lower()
        if _in_dict_simple(w):
            return True
        # Handle contractions across all supported languages:
        # FR/IT: l', d', n', s', c', j', m', t', qu', dell', nell', all', sull'
        # PT: n', d' (less common in modern PT)
        if "'" in w or "\u2019" in w:  # straight or curly apostrophe
            # Split on apostrophe and check the main part
            parts = _re.split(r"['\u2019]", w)
            # Filter out empty and very short prefixes (l, d, n, s, c, j, m, t, qu)
            main_parts = [p for p in parts if len(p) > 2]
            if main_parts and all(_in_dict_simple(p) for p in main_parts):
                return True
            # Also try: if everything after apostrophe is in dict
            # Covers FR l', d', n', s', c', j', m', t'
            # and IT l', d', un', quest'
            if len(parts) == 2 and len(parts[0]) <= 5 and _in_dict_simple(parts[1]):
                return True
        # Handle hyphenated compounds (all languages) and German-style prefixed words
        if any(c in w for c in '-\u2013\u2014'):
            parts = _re.split(r'[-\u2013\u2014]', w)
            parts = [p for p in parts if p]  # Remove empty
            if len(parts) >= 2 and all(_in_dict_simple(p) for p in parts):
                return True
        return False
    
    if low in _common_words or low_fixed in _common_words:
        return True
    _stripped = _ARTICLE_PREFIX_RE.sub("", clean)
    _stripped_fixed = _ARTICLE_PREFIX_RE.sub("", clean_fixed)
    if _stripped and (_stripped.lower() in _common_words or _stripped_fixed.lower() in _common_words):
        return True
    if len(clean) <= 2:
        return True
    if clean.isupper() and len(clean) <= 5:
        return True
    # Digit-starts → noise EXCEPT numbered companies with legal suffix
    if clean and clean[0].isdigit():
        if not LEGAL_SUFFIX_RE.search(clean):
            return True
    if clean.isdigit():
        return True
    words = clean.split()
    if len(words) == 1 and clean.isupper():
        return True
    if clean == clean.lower() and len(words) <= 2:
        return True
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    if len(words) >= 2 and not has_legal_suffix(clean) and all(
        _in_dict(w)
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
    ):
        return True
    # Strip parenthetical codes (e.g., "(NCSC)", "(ABC)") and standalone numbers/single letters
    # then check if what remains is all dictionary words. Catches regulatory/standard names.
    if len(words) >= 3 and not has_legal_suffix(clean):
        # Remove "(XXX)" patterns, standalone numbers, and single-letter words
        _code_stripped = _re.sub(r'\([A-Z0-9]{2,10}\)', '', clean)
        _code_stripped = _re.sub(r'\b\d+\b', '', _code_stripped)  # All digits
        _code_stripped = _re.sub(r"\b[a-zA-Z]['\u2019]?\s", ' ', _code_stripped)  # Single letter (possibly with apostrophe)
        _code_stripped = _re.sub(r'\s+', ' ', _code_stripped).strip()
        stripped_words = [w for w in _code_stripped.split() if w and len(w) > 1]
        if len(stripped_words) >= 2 and all(
            _in_dict(w)
            or all(c in "-\u2013\u2014/.," for c in w)
            for w in stripped_words
        ):
            return True
    if len(words) == 2 and words[0].lower() == "portion" and words[1].isdigit():
        return True
    if len(words) == 2 and words[0].lower() in (
        "le", "la", "les", "de", "du", "des", "au", "aux", "un", "une",
        "el", "los", "las", "il", "lo", "gli", "het",  # ES, IT, NL
        "der", "die", "das", "den", "dem", "des", "ein", "eine",  # DE
        "o", "a", "os", "as",  # PT
    ) and words[1].isupper() and len(words[1]) >= 2:
        return True
    if len(words) >= 2 and words[0].lower() in (
        "société", "societe",  # FR
        "sociedad", "empresa", "compañía", "compania",  # ES
        "società", "societa", "azienda", "impresa",  # IT
        "gesellschaft", "unternehmen", "firma",  # DE
        "vennootschap", "bedrijf", "onderneming",  # NL
        "sociedade", "empresa", "companhia",  # PT
    ):
        w1 = words[1].lower()
        _sentence_verbs = {
            # French
            "et", "ou", "qui", "que", "est", "a", "sont", "ont", "peut", "doit",
            "détermine", "determine", "présente", "presente", "utilise", "applique",
            "établit", "etablit", "calcule", "comptabilise", "reconnaît", "reconnait",
            "constate", "enregistre", "amortit", "provisionne", "rembourse",
            "détient", "detient", "possède", "possede", "gère", "gere",
            "exploite", "opère", "opere", "emploie", "embauche",
            "vend", "achète", "achete", "loue", "fabrique", "produit",
            "offre", "fournit", "distribue", "exporte", "importe",
            # English
            "is", "are", "has", "have", "can", "must", "should", "will",
            "determines", "presents", "uses", "applies", "calculates",
            "holds", "owns", "manages", "operates", "employs",
            "sells", "buys", "rents", "produces", "offers", "provides",
            # German
            "ist", "hat", "sind", "haben", "kann", "muss", "soll",
            "bestimmt", "verwendet", "berechnet", "hält", "haelt",
            "besitzt", "verwaltet", "betreibt", "beschäftigt", "beschaeftigt",
            "verkauft", "kauft", "mietet", "produziert", "bietet", "liefert",
            # Spanish
            "es", "ha", "son", "han", "puede", "debe",
            "determina", "presenta", "utiliza", "aplica", "calcula",
            "posee", "gestiona", "opera", "emplea",
            "vende", "compra", "alquila", "fabrica", "produce", "ofrece",
            # Italian
            "è", "ha", "sono", "hanno", "può", "puo", "deve",
            "determina", "presenta", "utilizza", "applica", "calcola",
            "detiene", "possiede", "gestisce", "opera", "impiega",
            "vende", "compra", "affitta", "fabbrica", "produce", "offre",
            # Dutch
            "is", "heeft", "zijn", "hebben", "kan", "moet",
            "bepaalt", "presenteert", "gebruikt", "berekent",
            "bezit", "beheert", "exploiteert",
            "verkoopt", "koopt", "huurt", "produceert", "biedt", "levert",
            # Portuguese
            "é", "tem", "são", "sao", "têm", "tem", "pode", "deve",
            "determina", "apresenta", "utiliza", "aplica", "calcula",
            "detém", "detem", "possui", "gere", "opera", "emprega",
            "vende", "compra", "aluga", "fabrica", "produz", "oferece",
        }
        if w1 in _sentence_verbs:
            return True
    if len(words) >= 3 and words[1].lower() in (
        # FR
        "est", "a", "sont", "ont", "peut", "doit",
        # EN
        "is", "are", "has", "have", "can", "must",
        # DE
        "ist", "hat", "sind", "haben", "kann", "muss",
        # ES
        "es", "ha", "son", "han", "puede", "debe",
        # IT
        "è", "ha", "sono", "hanno",
        # NL
        "is", "heeft", "zijn", "hebben",
        # PT
        "é", "tem", "são", "sao",
    ):
        return True
    if any(w.lower() in ("pour", "para", "für", "fuer", "per", "voor") for w in words):
        if not has_legal_suffix(clean):
            return True
    # For 3+ word phrases without legal suffix: if ALL words are dictionary
    # words, it's descriptive text, not a real organization name.
    # Real company names typically have proper nouns / non-dictionary words.
    # (With comprehensive dictionaries + stemming, we can require 100% match)
    if len(words) >= 3 and not has_legal_suffix(clean):
        if all(_in_dict(w) for w in words):
            return True
    if len(words) >= 3:
        low_words = [w.lower() for w in words]
        if any(w in low_words for w in (
            "catégorie", "categorie", "category", "kategorie",
            "categoría", "categoria",
        )):
            return True
    # Generic corporate references like "die AG", "der GmbH", "la SA":
    # text ending with article + bare legal suffix is not a real company name.
    if len(words) >= 3:
        penult = words[-2].lower()
        _articles = {
            "der", "die", "das", "den", "dem", "des", "ein", "eine",  # DE
            "le", "la", "les", "l'", "un", "une",  # FR
            "el", "la", "los", "las", "un", "una",  # ES
            "il", "lo", "la", "gli", "le", "un", "una",  # IT
            "de", "het", "een",  # NL
            "o", "a", "os", "as", "um", "uma",  # PT
            "the", "a", "an",  # EN
        }
        _bare_suffixes = {
            "ag", "gmbh", "kg", "kgaa", "ohg", "ug", "mbh", "se",
            "sa", "sarl", "sas", "srl", "spa", "snc",
            "inc", "corp", "llc", "ltd", "llp", "plc", "co", "lp",
            "bv", "nv",
        }
        if penult in _articles and words[-1].lower().rstrip(".") in _bare_suffixes:
            return True
    return False


# ── Shared domain noise (used by both PERSON and LOCATION filters) ──

_COMMON_DOMAIN_NOISE: frozenset[str] = frozenset({
    'aandoening', 'aandoeningen', 'aangeboren', 'aangifte', 'aangiften', 'aanslag',
    'aanslagen', 'aansprakelijkheid', 'abgabe', 'abgaben', 'abogado', 'abogados',
    'abschreibung', 'abschreibungen', 'absetzbar', 'absetzbarer', 'abzuege', 'abzug',
    'abzüge', 'acao', 'accantonamenti', 'accantonamento', 'accertamenti', 'accertamento',
    'accijns', 'accijnzen', 'accise', 'accises', 'accordi', 'accordo',
    'account', 'accounts', 'accrual', 'accruals', 'acoes', 'acordao',
    'acordo', 'acordos', 'acte', 'actes', 'actif', 'activa',
    'activo', 'activos', 'acuerdo', 'acuerdos', 'acute', 'acuto',
    'acuut', 'acórdão', 'addendum', 'adenda', 'aduana', 'aduanas',
    'advocaat', 'advocate', 'advocaten', 'advocates', 'advogado', 'advogados',
    'aenderung', 'aenderungen', 'aerzte', 'afdwingbaar', 'affidavit', 'affitti',
    'affitto', 'afschrijving', 'afschrijvingen', 'aftrek', 'aftrekbaar', 'agreement',
    'agreements', 'agudo', 'aigu', 'aigue', 'aiguë', 'akte',
    'akten', 'akut', 'alergia', 'alergias', 'alergico', 'alfandega',
    'alfândega', 'allergia', 'allergic', 'allergico', 'allergie', 'allergieen',
    'allergien', 'allergies', 'allergieën', 'allergique', 'allergisch', 'allergy',
    'alquiler', 'alquileres', 'alugueis', 'aluguel', 'aluguéis', 'alérgico',
    'ambulant', 'ambulatoire', 'ambulatorial', 'ambulatoriale', 'ambulatorio', 'ambulatory',
    'amendement', 'amendements', 'amendment', 'amendments', 'ammortamenti', 'ammortamento',
    'amortissement', 'amortissements', 'amortizacao', 'amortizacion', 'amortización', 'amortization',
    'amortização', 'amount', 'anaesthesie', 'anamnese', 'anamnesi', 'anamnesis',
    'anamnèse', 'anestesia', 'anesthesia', 'anesthesie', 'anesthetic', 'anesthésie',
    'angeboren', 'annexe', 'anwaelte', 'anwalt', 'anwälte', 'anästhesie',
    'apelacion', 'apelación', 'apotheek', 'apotheke', 'appeal', 'appeals',
    'appel', 'appelli', 'appello', 'appels', 'arancel', 'aranceles',
    'arbitrage', 'arbitragem', 'arbitraje', 'arbitration', 'arbitrato', 'arrendador',
    'arrendatario', 'arrendatário', 'arret', 'arrets', 'arrêt', 'arrêts',
    'arts', 'artsen', 'arzt', 'assessment', 'assessments', 'asset',
    'assets', 'assignation', 'assignee', 'assignor', 'ativo', 'atti',
    'attivo', 'atto', 'attore', 'attorney', 'attorneys', 'audit',
    'auditor', 'auditoria', 'auditors', 'auditoría', 'audits', 'aufwand',
    'aufwendungen', 'ausgabe', 'ausgaben', 'aussage', 'autopsia', 'autopsie',
    'autopsy', 'autor', 'autores', 'autópsia', 'avanzo', 'avenant',
    'avenants', 'avocat', 'avocats', 'avvocati', 'avvocato', 'ação',
    'ações', 'bailleur', 'balance', 'balanco', 'balans', 'balanço',
    'beeindiging', 'befreiung', 'befreiungen', 'beguenstigter', 'begunstigde', 'begünstigter',
    'behandeling', 'behandelingen', 'behandlung', 'behandlungen', 'behinderung', 'beklagter',
    'belastbaar', 'belasting', 'belastingen', 'belastingplichtige', 'benefice', 'benefices',
    'beneficiaire', 'beneficiaires', 'beneficiari', 'beneficiaries', 'beneficiario', 'beneficiarios',
    'beneficiary', 'beneficio', 'beneficios', 'beneficiário', 'beneficiários', 'benign',
    'benigno', 'benin', 'bepaling', 'bepalingen', 'beroep', 'berufung',
    'besmettelijk', 'besteuerung', 'bestimmung', 'bestimmungen', 'betraege', 'betrag',
    'beträge', 'bevoegdheid', 'beëindiging', 'bilan', 'bilancio', 'bilanz',
    'bindend', 'binding', 'biopsia', 'biopsie', 'biopsy', 'biópsia',
    'boekjaar', 'boesartig', 'breach', 'btw', 'buchung', 'buchungen',
    'bénin', 'bénéfice', 'bénéfices', 'bénéficiaire', 'bénéficiaires', 'bösartig',
    'caisse', 'caixa', 'caja', 'capitale', 'cardiologia', 'cardiologie',
    'cardiology', 'cardiología', 'cassa', 'causa', 'cause', 'cedant',
    'cedente', 'cesionario', 'cessionario', 'cessionnaire', 'cessionário', 'chapitre',
    'charge', 'charges', 'chirurg', 'chirurgen', 'chirurghi', 'chirurgia',
    'chirurgie', 'chirurgien', 'chirurgiens', 'chirurgies', 'chirurgo', 'chronic',
    'chronique', 'chronisch', 'cirugia', 'cirugía', 'cirujano', 'cirujanos',
    'cirurgia', 'cirurgiao', 'cirurgias', 'cirurgioes', 'cirurgião', 'cirurgiões',
    'civielrechtelijk', 'civil', 'civile', 'clause', 'clauses', 'clausola',
    'clausole', 'clausula', 'clausulas', 'clausule', 'clausules', 'clinica',
    'clinical', 'clinici', 'clinico', 'clinique', 'cliniques', 'cláusula',
    'cláusulas', 'clínica', 'clínico', 'collateral', 'competence', 'compliance',
    'compliant', 'compromiso', 'compromisos', 'compromisso', 'compromissos', 'compte',
    'comptes', 'compétence', 'condition', 'conditions', 'conduttore', 'conforme',
    'conformidade', 'conformita', 'conformite', 'conformità', 'conformité', 'congenital',
    'congenito', 'congénital', 'congénito', 'congênito', 'constitutional', 'conta',
    'contas', 'contentieux', 'contenzioso', 'conti', 'conto', 'contract',
    'contracten', 'contracts', 'contractual', 'contractuales', 'contractueel', 'contractuel',
    'contractuele', 'contractuelle', 'contractuelles', 'contractuels', 'contraparte', 'contrat',
    'contrato', 'contratos', 'contrats', 'contratti', 'contratto', 'contrattuale',
    'contrattuali', 'contratuais', 'contratual', 'contrepartie', 'contribuable', 'contribuables',
    'contribuente', 'contribuenti', 'contribuinte', 'contribuintes', 'contribuyente', 'contribuyentes',
    'controle', 'controparte', 'convenio', 'convenios', 'convention', 'conventions',
    'convenuto', 'convenzione', 'convenzioni', 'conveyance', 'convênio', 'convênios',
    'corporel', 'corporelle', 'corporelles', 'corporels', 'counsel', 'counterparty',
    'court', 'courts', 'cout', 'couts', 'covenant', 'covenants',
    'coût', 'coûts', 'creance', 'creances', 'credit', 'crediti',
    'credito', 'creditos', 'criminal', 'cronico', 'créance', 'créances',
    'crédit', 'crédito', 'créditos', 'crónico', 'crônico', 'cuenta',
    'cuentas', 'cumplimiento', 'customs', 'cédant', 'dazi', 'dazio',
    'debit', 'debiti', 'debito', 'declaration', 'declarations', 'decree',
    'decrees', 'decreet', 'decret', 'decreti', 'decreto', 'decretos',
    'decrets', 'deducao', 'deduccion', 'deducciones', 'deducción', 'deducibile',
    'deducible', 'deducibles', 'deductible', 'deduction', 'deductions', 'dedutivel',
    'dedutível', 'deduzione', 'deduzioni', 'dedução', 'deed', 'deeds',
    'default', 'defaut', 'defence', 'defendant', 'defendants', 'defendeur',
    'defendeurs', 'defense', 'deficiencia', 'deficit', 'deficiência', 'demanda',
    'demandado', 'demandados', 'demandante', 'demandantes', 'demandas', 'demandeur',
    'demandeurs', 'depense', 'depenses', 'deposition', 'deposizione', 'depreciacao',
    'depreciacion', 'depreciación', 'depreciation', 'depreciação', 'dermatologia', 'dermatologie',
    'dermatology', 'dermatología', 'despesa', 'despesas', 'dette', 'dettes',
    'deuda', 'deudas', 'diagnose', 'diagnosen', 'diagnoses', 'diagnosi',
    'diagnosis', 'diagnostic', 'diagnostico', 'diagnosticos', 'diagnostics', 'diagnóstico',
    'diagnósticos', 'dichiarazione', 'dichiarazioni', 'disabilita', 'disabilities', 'disability',
    'disabilità', 'disavanzo', 'discapacidad', 'disease', 'diseases', 'divida',
    'dividas', 'dividend', 'dividende', 'dividenden', 'dividendes', 'dividendi',
    'dividendo', 'dividendos', 'docteur', 'docteurs', 'doctor', 'doctores',
    'doenca', 'doencas', 'doença', 'doenças', 'dosage', 'dosagem',
    'dosaggio', 'dose', 'dosering', 'dosierung', 'dosificacion', 'dosificación',
    'dosis', 'dotation', 'dotations', 'dottore', 'dottoressa', 'dottori',
    'douane', 'douanes', 'doutor', 'doutora', 'doutores', 'droit',
    'droits', 'duties', 'duty', 'débit', 'déclaration', 'déclarations',
    'décret', 'décrets', 'déductible', 'déduction', 'déductions', 'défaut',
    'défendeur', 'défendeurs', 'déficit', 'dépense', 'dépenses', 'déposition',
    'dívida', 'dívidas', 'eccedenza', 'eidesstattlich', 'einbehaltung', 'eingriff',
    'eingriffe', 'einkommensteuer', 'einnahme', 'einnahmen', 'eiser', 'eisers',
    'ejecutable', 'ejercicio', 'emenda', 'emendamenti', 'emendamento', 'emendas',
    'emergencia', 'emergenza', 'emergência', 'emprunt', 'enacted', 'encumbrance',
    'encumbrances', 'enfermedad', 'enfermedades', 'enfermeira', 'enfermeiras', 'enfermeiro',
    'enfermeiros', 'enfermera', 'enfermeras', 'enfermero', 'enfermeros', 'enforceable',
    'engagement', 'engagements', 'enmienda', 'enmiendas', 'entrata', 'entrate',
    'entschaedigung', 'entschädigung', 'epidemia', 'epidemic', 'epidemie', 'equipment',
    'erario', 'erblich', 'ereditario', 'erfelijk', 'ergebnis', 'erlass',
    'erlasse', 'erstattung', 'erstattungen', 'ertraege', 'ertrag', 'erträge',
    'esame', 'esami', 'escritura', 'escrituras', 'esecutivo', 'esenzione',
    'esenzioni', 'esercizio', 'estipulacao', 'estipulacion', 'estipulaciones', 'estipulación',
    'estipulação', 'estoque', 'estoques', 'exame', 'examen', 'examenes',
    'examens', 'exames', 'examination', 'examinations', 'excedent', 'excise',
    'excédent', 'executeur', 'executoire', 'executor', 'executors', 'exemption',
    'exemptions', 'exencion', 'exenciones', 'exención', 'exequivel', 'exequível',
    'exercicio', 'exercício', 'existencias', 'exoneration', 'exonerations', 'exonération',
    'exonérations', 'expense', 'exámenes', 'exécuteur', 'exécutoire', 'factura',
    'facturas', 'facture', 'facturen', 'factures', 'factuur', 'fallo',
    'fallos', 'farmaceutico', 'farmaceutisch', 'farmaci', 'farmacia', 'farmaco',
    'farmacéutico', 'farmacêutico', 'farmácia', 'fattura', 'fatture', 'fatura',
    'faturas', 'fiduciaire', 'fiduciario', 'fiduciary', 'fiduciário', 'filing',
    'finanzamt', 'firmante', 'firmantes', 'firmatari', 'firmatario', 'fiscaal',
    'fiscais', 'fiscal', 'fiscale', 'fiscales', 'fiscali', 'fiscalia',
    'fiscalite', 'fiscalité', 'fiscalía', 'fiscaux', 'fisco', 'fiskalisch',
    'fiskalische', 'fondi', 'fondo', 'fondos', 'fonds', 'fondsen',
    'forderung', 'forderungen', 'fund', 'fundo', 'fundos', 'funds',
    'furniture', 'gain', 'gains', 'garantia', 'garantias', 'garantie',
    'garanties', 'garantía', 'garantías', 'garanzia', 'garanzie', 'gasto',
    'gastos', 'geburtshilfe', 'gedaagde', 'gedaagden', 'gegenpartei', 'gehaelter',
    'gehalt', 'gehälter', 'geneesmiddel', 'geneesmiddelen', 'gerechtelijk', 'gericht',
    'gerichte', 'gerichtlich', 'gesetz', 'gesetze', 'gesetzgebung', 'gewaehrleistung',
    'gewinn', 'gewährleistung', 'ginecologia', 'ginecología', 'giudice', 'giudici',
    'giudizi', 'giudizio', 'giuridica', 'giuridici', 'giuridico', 'giurisdizione',
    'giurisprudenza', 'goedaardig', 'governing', 'gravamen', 'gravamenes', 'gravámenes',
    'greffe', 'greffes', 'grundpfandrecht', 'grundschuld', 'gutartig', 'gynaecologie',
    'gynaekologie', 'gynecological', 'gynecologie', 'gynecology', 'gynäkologie', 'gynécologie',
    'hacienda', 'haftung', 'handicap', 'heffing', 'heffingen', 'hereditaire',
    'hereditario', 'hereditary', 'hereditário', 'hipoteca', 'homologation', 'honoraire',
    'honoraires', 'hopital', 'hopitaux', 'hospitais', 'hospital', 'hospitales',
    'hospitals', 'huren', 'huur', 'huurder', 'hypotheekrecht', 'hypotheque',
    'hypothèque', 'héréditaire', 'hôpital', 'hôpitaux', 'illness', 'immobilier',
    'immunisatie', 'immunisation', 'immunisations', 'immunization', 'immunizations', 'immunizzazione',
    'impegni', 'impegno', 'impfstoff', 'impfstoffe', 'impfung', 'impfungen',
    'imponibile', 'imponible', 'imponibles', 'imposable', 'imposables', 'imunizacao',
    'imunização', 'inadempimento', 'inadimplemento', 'income', 'incorporel', 'incorporelle',
    'incorporelles', 'incorporels', 'incumplimiento', 'indemnification', 'indemnisation', 'indemnite',
    'indemnity', 'indemnité', 'indemnizacao', 'indemnizacion', 'indemnización', 'indemnização',
    'indenizacao', 'indenização', 'indennita', 'indennità', 'indennizzo', 'infeccao',
    'infeccion', 'infecciones', 'infeccioso', 'infección', 'infeccoes', 'infectie',
    'infecties', 'infectieuse', 'infectieux', 'infection', 'infections', 'infectious',
    'infecção', 'infecções', 'infektioes', 'infektion', 'infektionen', 'infektiös',
    'infermiera', 'infermiere', 'infermieri', 'infettivo', 'infezione', 'infezioni',
    'infirmier', 'infirmiere', 'infirmiers', 'infirmière', 'ingreep', 'ingrepen',
    'ingreso', 'ingresos', 'inhouding', 'injonction', 'injunction', 'inkomst',
    'inkomsten', 'inkomstenbelasting', 'inmunizacion', 'inmunización', 'inpatient', 'inquilino',
    'interes', 'intereses', 'interesse', 'interessi', 'interet', 'interets',
    'intervencao', 'intervencion', 'intervención', 'interventi', 'intervention', 'interventions',
    'intervento', 'intervenção', 'interés', 'intérêt', 'intérêts', 'invaliditaet',
    'invalidite', 'invaliditeit', 'invalidität', 'invalidité', 'inventar', 'inventario',
    'inventaris', 'inventário', 'ipoteca', 'ipoteche', 'irrevocabile', 'irrevocable',
    'irrevogavel', 'irrevogável', 'irrévocable', 'isencao', 'isencoes', 'isenção',
    'isenções', 'iva', 'judgment', 'judgments', 'jueces', 'juez',
    'jugement', 'jugements', 'juiz', 'juizes', 'juridica', 'juridico',
    'juridique', 'juridiques', 'juridisch', 'juridische', 'jurisdicao', 'jurisdiccion',
    'jurisdicción', 'jurisdictie', 'jurisdiction', 'jurisdição', 'jurisprudence', 'jurisprudencia',
    'jurisprudentie', 'jurisprudência', 'juro', 'juros', 'jurídica', 'jurídico',
    'juízes', 'kapitaal', 'kardiologie', 'kas', 'kasse', 'kindergeneeskunde',
    'kinderheilkunde', 'klaeger', 'klage', 'klagen', 'klausel', 'klauseln',
    'klinik', 'kliniken', 'klinisch', 'klinische', 'kläger', 'koerperschaftsteuer',
    'konten', 'konto', 'kosten', 'krankenhaeuser', 'krankenhaus', 'krankenhäuser',
    'krankenpfleger', 'krankenschwester', 'krankheit', 'krankheiten', 'kuendigung', 'kwaadaardig',
    'körperschaftsteuer', 'kündigung', 'labor', 'laboratoire', 'laboratoires', 'laboratori',
    'laboratoria', 'laboratories', 'laboratorio', 'laboratorios', 'laboratorium', 'laboratory',
    'laboratório', 'laboratórios', 'labore', 'lancamento', 'landlord', 'lançamento',
    'lawsuit', 'lawsuits', 'lawyer', 'lawyers', 'ledger', 'ledgers',
    'legais', 'legal', 'legale', 'legales', 'legali', 'legge',
    'leggi', 'legislacao', 'legislacion', 'legislación', 'legislation', 'legislative',
    'legislazione', 'legislação', 'lei', 'leis', 'lessee', 'lessor',
    'levies', 'levy', 'ley', 'leyes', 'liabilities', 'liability',
    'lien', 'liens', 'liquidacion', 'liquidación', 'litigation', 'litigio',
    'litigios', 'litígio', 'litígios', 'locataire', 'locatario', 'locatore',
    'locatário', 'locazione', 'loehne', 'lohn', 'loi', 'lois',
    'lonen', 'loon', 'loss', 'loyer', 'loyers', 'lucro',
    'lucros', 'législation', 'löhne', 'maladie', 'maladies', 'malattia',
    'malattie', 'malignant', 'maligne', 'maligno', 'malin', 'manquement',
    'medecin', 'medecins', 'medica', 'medical', 'medicale', 'medicament',
    'medicamento', 'medicamentos', 'medicaments', 'medication', 'medications', 'mediche',
    'medici', 'medicijn', 'medicijnen', 'medico', 'medikament', 'medikamente',
    'medisch', 'medische', 'medizinisch', 'medizinische', 'medizinischer', 'miete',
    'mieten', 'mieter', 'mobilier', 'montant', 'médecin', 'médecins',
    'médica', 'médical', 'médicale', 'médicament', 'médicaments', 'médico',
    'nachlassgericht', 'nachtraege', 'nachtrag', 'nachträge', 'naleving', 'narcose',
    'narkose', 'net', 'nets', 'nette', 'nettes', 'neurologia',
    'neurologie', 'neurology', 'neurología', 'notaufnahme', 'note', 'notes',
    'notfall', 'nurse', 'nurses', 'nursing', 'obblighi', 'obbligo',
    'obduktion', 'obligacion', 'obligaciones', 'obligación', 'obligation', 'obligations',
    'obrigacao', 'obrigacoes', 'obrigação', 'obrigações', 'obstetric', 'obstetricia',
    'obstetrics', 'obstetrique', 'obstetrícia', 'obstétrique', 'oncologia', 'oncologie',
    'oncology', 'oncología', 'ondertekenaar', 'onderzoek', 'onderzoeken', 'onherroepelijk',
    'onkologie', 'onus', 'operacao', 'operatie', 'operaties', 'operation',
    'operationen', 'operazione', 'operazioni', 'operação', 'ordenanca', 'ordenanza',
    'ordenanzas', 'ordenança', 'ordinance', 'ordinances', 'ordinanza', 'ordinanze',
    'orthopadie', 'orthopedic', 'orthopedics', 'orthopedie', 'orthopedique', 'orthopädie',
    'orthopédique', 'ortopedia', 'ortopedico', 'ortopédico', 'ospedale', 'ospedali',
    'ostetricia', 'outpatient', 'overeenkomst', 'overeenkomsten', 'overschot', 'pacht',
    'pachter', 'paciente', 'pacientes', 'pacto', 'pactos', 'paechter',
    'paediatrie', 'page', 'pandemia', 'pandemic', 'pandemie', 'pandrecht',
    'pandémie', 'partida', 'partidas', 'pasivo', 'pasivos', 'passif',
    'passiva', 'passivo', 'pathologie', 'pathologies', 'pathology', 'patient',
    'patienten', 'patientin', 'patientinnen', 'patiënt', 'patiënten', 'patologia',
    'patologias', 'patologie', 'patología', 'patrimonio', 'patrimônio', 'patti',
    'patto', 'payable', 'payables', 'paziente', 'pazienti', 'pediatria',
    'pediatric', 'pediatrico', 'pediatrics', 'pediatrie', 'pediatrique', 'pediatría',
    'pediátrico', 'pegno', 'penal', 'penale', 'perdida', 'perdidas',
    'perdita', 'perdite', 'pfandrecht', 'pflicht', 'pflichten', 'pharmaceutical',
    'pharmaceuticals', 'pharmaceutique', 'pharmaceutiques', 'pharmacie', 'pharmacy', 'pharmazeutisch',
    'physician', 'physicians', 'plaintiff', 'plaintiffs', 'posologie', 'poursuite',
    'poursuites', 'praeambel', 'praemie', 'praemien', 'preamble', 'preambolo',
    'preambule', 'preambulo', 'precedent', 'precedente', 'precedents', 'prejuizo',
    'prejuízo', 'prelievi', 'prelievo', 'premi', 'premie', 'premies',
    'premio', 'premios', 'premium', 'premiums', 'preneur', 'prescription',
    'prescriptions', 'preámbulo', 'preâmbulo', 'prima', 'primas', 'prime',
    'primes', 'privilege', 'privilège', 'probate', 'procedimenti', 'procedimento',
    'procedimentos', 'procedimiento', 'procedimientos', 'procedure', 'procedures', 'proceeding',
    'proceedings', 'proces', 'procurador', 'procuradores', 'procès', 'procédure',
    'procédures', 'produit', 'produits', 'profit', 'prognose', 'prognosi',
    'prognosis', 'prognostico', 'prognóstico', 'promulgue', 'promulgué', 'pronostic',
    'pronostico', 'pronóstico', 'proprietaire', 'propriétaire', 'prosecution', 'prosthesis',
    'protese', 'proteses', 'protesi', 'protesis', 'prothese', 'prothesen',
    'protheses', 'prothèse', 'prothèses', 'provisao', 'provision', 'provisiones',
    'provisions', 'provisión', 'provisoes', 'provisão', 'provisões', 'präambel',
    'prämie', 'prämien', 'préambule', 'précédent', 'prêmio', 'prêmios',
    'prótese', 'próteses', 'prótesis', 'psichiatria', 'psiquiatria', 'psiquiatría',
    'psychiatrie', 'psychiatry', 'pächter', 'pädiatrie', 'pédiatrie', 'pédiatrique',
    'pénal', 'pérdida', 'pérdidas', 'radiologia', 'radiologie', 'radiology',
    'radiología', 'rate', 'reabilitacao', 'reabilitação', 'receita', 'receitas',
    'receivable', 'receivables', 'recept', 'recepten', 'receta', 'recetas',
    'recette', 'recettes', 'rechtbank', 'rechtbanken', 'rechter', 'rechters',
    'rechtlich', 'rechtliche', 'rechtlicher', 'rechtsanwaelte', 'rechtsanwalt', 'rechtsanwälte',
    'rechtsprechung', 'rechtszaak', 'rechtszaken', 'recital', 'recitals', 'recurso',
    'recursos', 'reeducation', 'refund', 'refunds', 'reglamento', 'reglamentos',
    'reglement', 'reglementaire', 'reglements', 'regolamenti', 'regolamento', 'regulacion',
    'regulación', 'regulamento', 'regulamentos', 'regulation', 'regulations', 'regulatory',
    'regulierung', 'reha', 'rehabilitacion', 'rehabilitación', 'rehabilitation', 'rekening',
    'rekeningen', 'remboursement', 'remboursements', 'remision', 'remisión', 'remissao',
    'remissie', 'remission', 'remissione', 'remissão', 'renta', 'rentas',
    'rente', 'rescisao', 'rescision', 'rescisión', 'rescisão', 'resiliation',
    'resolucion', 'resolución', 'responsabilidad', 'responsabilidade', 'responsabilidades', 'responsabilita',
    'responsabilite', 'responsabilità', 'responsabilité', 'resultaat', 'resultado', 'resultados',
    'resultat', 'resultaten', 'retencao', 'retencion', 'retenciones', 'retención',
    'retencoes', 'retenção', 'retenções', 'return', 'returns', 'reu',
    'reus', 'revalidatie', 'revenu', 'revenue', 'revenus', 'revisione',
    'revisioni', 'rezept', 'rezepte', 'riabilitazione', 'ricetta', 'ricette',
    'richter', 'rimborsi', 'rimborso', 'risoluzione', 'risultati', 'risultato',
    'ritenuta', 'ritenute', 'ruecklage', 'ruecklagen', 'rueckstellung', 'rueckstellungen',
    'ruling', 'rulings', 'rupture', 'règlement', 'règlements', 'réglementaire',
    'réhabilitation', 'rémission', 'résiliation', 'résultat', 'réu', 'réus',
    'rééducation', 'rücklage', 'rücklagen', 'rückstellung', 'rückstellungen', 'salaire',
    'salaires', 'salari', 'salario', 'salarios', 'salaris', 'salarissen',
    'saldo', 'salário', 'salários', 'satzung', 'satzungen', 'schadeloosstelling',
    'schadensersatz', 'schatkist', 'schending', 'schiedsverfahren', 'schuld', 'schulden',
    'section', 'sentenca', 'sentencas', 'sentencia', 'sentencias', 'sentenza',
    'sentenze', 'sentença', 'sentenças', 'signataire', 'signataires', 'signatario',
    'signatories', 'signatory', 'signatário', 'sintoma', 'sintomas', 'sintomi',
    'sintomo', 'solde', 'spesa', 'spese', 'spoedafdeling', 'spoedeisend',
    'staatsanwalt', 'staatsanwaltschaft', 'stationaer', 'stationär', 'statute', 'statutes',
    'statutory', 'steuer', 'steuererklaerung', 'steuererklärung', 'steuern', 'steuerpflichtig',
    'steuerpflichtiger', 'stipendi', 'stipendio', 'stipulation', 'stipulations', 'stipulazione',
    'stipulazioni', 'strafrechtelijk', 'strafrechtlich', 'subpoena', 'subvention', 'subventions',
    'sueldo', 'sueldos', 'summons', 'superavit', 'superávit', 'surgeon',
    'surgeons', 'surgeries', 'surgery', 'surplus', 'symptom', 'symptome',
    'symptomen', 'symptomes', 'symptoms', 'symptoom', 'symptôme', 'symptômes',
    'síntoma', 'síntomas', 'tableau', 'tarief', 'tarieven', 'tarif',
    'tarifa', 'tarifas', 'tariff', 'tariffa', 'tariffe', 'tariffs',
    'tarifs', 'tassazione', 'taux', 'tax', 'taxable', 'taxation',
    'taxes', 'taxpayer', 'taxpayers', 'tegenpartij', 'tekort', 'temoignage',
    'tenant', 'terapeutico', 'terapia', 'terapias', 'terapie', 'terapéutico',
    'terapêutico', 'termination', 'teruggave', 'tesoreria', 'tesorería', 'tesouraria',
    'testamentsvollstrecker', 'testimonianza', 'testimony', 'therapeutic', 'therapeutique', 'therapeutisch',
    'therapie', 'therapieen', 'therapien', 'therapies', 'therapieën', 'therapy',
    'thérapeutique', 'thérapie', 'thérapies', 'titre', 'titres', 'total',
    'traitement', 'traitements', 'transfusao', 'transfusie', 'transfusion', 'transfusión',
    'transfusão', 'transplant', 'transplantatie', 'transplantaties', 'transplantation', 'transplantationen',
    'transplante', 'transplantes', 'transplants', 'trapianti', 'trapianto', 'trasfusione',
    'trasplante', 'trasplantes', 'tratamento', 'tratamentos', 'tratamiento', 'tratamientos',
    'trattamenti', 'trattamento', 'treasury', 'treatment', 'treatments', 'tresorerie',
    'treuhaender', 'treuhänder', 'tribunais', 'tribunal', 'tribunale', 'tribunales',
    'tribunali', 'tribunals', 'tribunaux', 'tributacao', 'tributacion', 'tributación',
    'tributaria', 'tributario', 'tributavel', 'tributação', 'tributo', 'tributos',
    'tributária', 'tributário', 'tributável', 'trustee', 'trustees', 'trésorerie',
    'turnover', 'tva', 'témoignage', 'ueberschuss', 'uitgave', 'uitgaven',
    'uitspraak', 'umsaetze', 'umsatz', 'umsatzsteuer', 'umsätze', 'undertaking',
    'undertakings', 'untersuchung', 'untersuchungen', 'unterzeichner', 'unwiderruflich', 'urgence',
    'urgences', 'urgencia', 'urgencias', 'urkunde', 'urkunden', 'urteil',
    'urteile', 'utile', 'vaccin', 'vaccinatie', 'vaccinaties', 'vaccination',
    'vaccinations', 'vaccinazione', 'vaccinazioni', 'vaccine', 'vaccines', 'vaccini',
    'vaccino', 'vaccins', 'vacina', 'vacinacao', 'vacinas', 'vacinação',
    'vacuna', 'vacunacion', 'vacunación', 'vacunas', 'valeur', 'valeurs',
    'vat', 'vennootschapsbelasting', 'veranlagung', 'verbindlich', 'verbintenis', 'verbintenissen',
    'verdetto', 'verdict', 'verdicts', 'veredicto', 'veredictos', 'vereinbarung',
    'vereinbarungen', 'verfahren', 'verfuegung', 'verfügung', 'verhuurder', 'verlies',
    'verloskunde', 'verlust', 'vermieter', 'vermoegen', 'vermogen', 'vermögen',
    'verordening', 'verordeningen', 'verordnung', 'verordnungen', 'verpachter', 'verpflichtung',
    'verpflichtungen', 'verpleegkundige', 'verpleegkundigen', 'verpleger', 'verplichting', 'verplichtingen',
    'verstoss', 'verstoß', 'verteidigung', 'vertraege', 'vertrag', 'vertragliche',
    'vertraglicher', 'verträge', 'vincolante', 'vinculante', 'vinculativo', 'voce',
    'voci', 'vollstreckbar', 'vollstrecker', 'vonnis', 'vonnissen', 'voorraad',
    'voorraden', 'voorschrift', 'voorschriften', 'voorziening', 'voorzieningen', 'vordering',
    'vorderingen', 'vorraete', 'vorräte', 'vorschrift', 'vorschriften', 'vrijstelling',
    'vrijstellingen', 'vrijwaring', 'warranties', 'warranty', 'wet', 'wetgeving',
    'wetten', 'wijziging', 'wijzigingen', 'winst', 'wirtschaftspruefer', 'wirtschaftsprüfer',
    'withholding', 'ziekenhuis', 'ziekenhuizen', 'ziekte', 'ziekten', 'zins',
    'zinsen', 'zivilrechtlich', 'zoll', 'zustaendigkeit', 'zuständigkeit', 'änderung',
    'änderungen', 'ärzte', 'épidémie', 'ônus', 'überschuss',
})


# ── LOCATION-only noise (building / facility terms) ──

_LOC_ONLY_NOISE: frozenset[str] = frozenset({
    'almacen', 'almacenes', 'almacén', 'amounts', 'anlage', 'anlagen',
    'apparatuur', 'arena', 'arenas', 'arenes', 'armazem', 'armazens',
    'armazém', 'armazéns', 'arquibancada', 'arquibancadas', 'arredamento', 'arènes',
    'aréna', 'atelier', 'ateliers', 'attrezzatura', 'attrezzature', 'ausstattung',
    'batiment', 'batiments', 'buero', 'building', 'buildings', 'bâtiment',
    'bâtiments', 'büro', 'campi', 'campo', 'campo de juego', 'campos',
    'cancha', 'canchas', 'capannone', 'capannoni', 'club', 'clubhouse',
    'clubs', 'complex', 'complexe', 'credits', 'debt', 'debts',
    'dividends', 'edifici', 'edificio', 'edificios', 'edifício', 'edifícios',
    'einrichtung', 'emprunts', 'entrepot', 'entrepots', 'entrepôt', 'entrepôts',
    'equipamento', 'equipamentos', 'equipamiento', 'equities', 'equity', 'estadio',
    'estadios', 'estádio', 'estádios', 'expenses', 'exploitation', 'fabrica',
    'fabriek', 'fabrik', 'facilities', 'facility', 'financement', 'fábrica',
    'garage', 'garages', 'gebaeude', 'gebaude', 'gebouw', 'gebouwen',
    'gebäude', 'gelaende', 'gelände', 'gimnasio', 'ginasio', 'ginásio',
    'grada', 'gradas', 'gradinata', 'gradinate', 'gradins', 'grandstand',
    'grandstands', 'grundstueck', 'grundstück', 'guarantee', 'guarantees', 'gymnase',
    'gymnasium', 'hal', 'hallen', 'hangar', 'hangars', 'haupttribuene',
    'haupttribüne', 'immobilisation', 'immobilisations', 'impianti', 'impianto', 'instalacao',
    'instalacion', 'instalaciones', 'instalación', 'instalacoes', 'instalação', 'instalações',
    'interest', 'interests', 'investissement', 'invoice', 'invoices', 'kantoor',
    'kantoren', 'lager', 'lagerhalle', 'local', 'locale', 'locales',
    'locali', 'locaux', 'losses', 'magasin', 'magasins', 'magazijn',
    'magazijnen', 'magazzini', 'magazzino', 'meubilair', 'mobiliario', 'mobiliário',
    'moebel', 'mortgage', 'mortgages', 'möbel', 'nautique', 'nave',
    'naves', 'officina', 'officine', 'oficina', 'oficinas', 'ordonnance',
    'ordonnances', 'palasport', 'palazzetto', 'pand', 'panden', 'parking',
    'parkings', 'patients', 'pelouse', 'piscina', 'piscine', 'pitch',
    'polideportivo', 'pool', 'premises', 'profiverein', 'profivereine', 'profivereins',
    'rates', 'recinto', 'recintos', 'rent', 'rental', 'rents',
    'resultats', 'revenues', 'ruimte', 'ruimten', 'résultats', 'salaries',
    'salary', 'salle', 'salles', 'schwimmbad', 'sede', 'sedes',
    'solar', 'solares', 'spielfeld', 'spielstaette', 'spielstätte', 'sportcomplex',
    'sporthal', 'sportplatz', 'stabilimenti', 'stabilimento', 'stade', 'stades',
    'stadi', 'stadio', 'stadion', 'stadiongelaende', 'stadiongelände', 'stadium',
    'stadiums', 'stock', 'stocks', 'subsidies', 'subsidy', 'taller',
    'talleres', 'terrain', 'terrain de jeu', 'terrains', 'terrein', 'terreinen',
    'terreni', 'terreno', 'terrenos', 'tribuene', 'tribuna', 'tribunas',
    'tribune', 'tribunes', 'tribüne', 'turnhalle', 'usine', 'usines',
    'veld', 'velden', 'venue', 'venues', 'vereinsgelaende', 'vereinsgelände',
    'vereinsheim', 'wage', 'wages', 'warehouse', 'werkplaats', 'werkstaette',
    'werkstatt', 'werkstätte', 'workshop', 'zwembad',
})


# ── PERSON-only noise (notarial / document terms) ──

_PERSON_ONLY_NOISE: frozenset[str] = frozenset({
    'aandeelhouder', 'aandeelhouders', 'abaixo-assinado', 'abschnitt', 'accionista', 'accionistas',
    'acionista', 'acionistas', 'acquisition', 'acquisitions', 'afdeling', 'aforementioned',
    'aforesaid', 'algemene vergadering', 'allegato', 'anexo', 'anhang', 'anmerkung',
    'antedicho', 'approssimativamente', 'approximately', 'aproximadamente', 'assemblea generale', 'assemblee generale',
    'assembleia geral', 'assemblée générale', 'ativos', 'autenticada', 'autenticado', 'autenticata',
    'autenticato', 'authenticated', 'authentifie', 'authentifié', 'azionista', 'azionisti',
    'beurkundet', 'beurkundeten', 'beurkundeter', 'beurkundung', 'bijlage', 'bovengenoemd',
    'capital', 'capitolo', 'capitulo', 'capítulo', 'certificada', 'certificado',
    'certificata', 'certificato', 'certifie', 'certified', 'certifié', 'ci-apres',
    'ci-après', 'ci-dessous', 'ci-dessus', 'clos', 'clôt', 'commercial register',
    'comptable', 'comptables', 'conclusion', 'conformement', 'conformemente', 'conformément',
    'courant', 'courante', 'courantes', 'courants', 'destinataire', 'entsprechend',
    'environ', 'ergebnisse', 'exercice', 'financier', 'financiere', 'financieres',
    'financiers', 'financière', 'financières', 'foregoing', 'formwechselnd', 'gecertificeerd',
    'gelegaliseerd', 'gesamt', 'gesellschafterbeschluss', 'gewaarmerkt', 'grundsaetzlich', 'grundsätzlich',
    'handelsregister', 'hereby', 'hereinafter', 'hereunder', 'herewith', 'hierbij',
    'hoofdstuk', 'imposta', 'imposte', 'imposto', 'impostos', 'impot',
    'impots', 'impuesto', 'impuestos', 'impôt', 'impôts', 'infrascrito',
    'insgesamt', 'introduction', 'junta general', 'kapital', 'kapitel', 'lave-vaisselle',
    'lecteur', 'lecteurs', 'lectrice', 'lectrices', 'location', 'location-acquisition',
    'massgeblich', 'maßgeblich', 'mediante', 'mehrwertsteuer', 'mencionado', 'nachfolgend',
    'noot', 'nota', 'notarial', 'notarialmente', 'notarie', 'notariee',
    'notarieel', 'notariees', 'notariele', 'notariell', 'notaries', 'notarile',
    'notarised', 'notarized', 'notarié', 'notariée', 'notariées', 'notariés',
    'notariële', 'notiz', 'ondergetekende', 'ongeveer', 'opmerking', 'overeenkomstig',
    'overwegend', 'pagina', 'passivos', 'poste', 'postes', 'predetto',
    'prelevement', 'prelevements', 'prélèvement', 'prélèvements', 'pursuant', 'página',
    'registo comercial', 'registre du commerce', 'registro comercial', 'registro delle imprese', 'registro mercantil', 'reprise',
    'reprises', 'respectievelijk', 'respectivamente', 'respectively', 'respectivement', 'respetivamente',
    'retenue', 'retenues', 'rispettivamente', 'secao', 'seccion', 'sección',
    'seite', 'sezione', 'seção', 'shareholder', 'shareholders', 'sommaire',
    'sostanzialmente', 'sottoscritta', 'sottoscritto', 'soussigne', 'soussignee', 'soussigné',
    'soussignée', 'subscrita', 'subscrito', 'substancialmente', 'substantially', 'substantiellement',
    'suddetta', 'suddetto', 'summenzionato', 'supracitado', 'supramencionado', 'suscrito',
    'susmentionne', 'susmentionné', 'susodicho', 'sustancialmente', 'susvise', 'susvisé',
    'tabel', 'tabela', 'tabella', 'tabelle', 'tabla', 'taxe',
    'totaal', 'totale', 'trade register', 'umgewandelt', 'undersigned', 'utilisateur',
    'utilisatrice', 'voornoemd', 'vorstehend', 'wesentlich', 'whereas',
})


# Compose the full sets from shared + type-specific terms
_LOC_PIPELINE_NOISE: frozenset[str] = _COMMON_DOMAIN_NOISE | _LOC_ONLY_NOISE
_PERSON_PIPELINE_NOISE: frozenset[str] = _COMMON_DOMAIN_NOISE | _PERSON_ONLY_NOISE


def _is_loc_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy LOCATION false-positive."""
    clean = text.strip()
    low = clean.lower()
    if low in _LOC_PIPELINE_NOISE:
        return True
    if len(clean) <= 2:
        return True
    if clean.isdigit():
        return True
    if clean and clean[0].isdigit():
        return True
    if _re.match(r"^location\s+(?:de|d[''])", low):
        return True
    # Strip leading articles/prepositions (FR, ES, IT, PT, DE, NL)
    _stripped = _re.sub(
        r"^(?:[Ll][eao]s?|[Dd][eiu]s?|[Uu]n[ea]?|[Ll]['']\s*|[Dd]['']\s*"  # FR
        r"|[Ee]l|[Ll]os|[Ll]as"  # ES
        r"|[Ii]l|[Gg]li|[Ll][oae]|[Uu]n[oa]?"  # IT
        r"|[Dd][aeo]s?|[Oo]s?|[Aa]s?"  # PT
        r"|[Dd](?:er|ie|as|en|em|es)|[Ee]in[e]?"  # DE
        r"|[Hh]et|[Dd]e|[Ee]en"  # NL
        r")\s+", "", clean)
    if _stripped and _stripped.lower() in _LOC_PIPELINE_NOISE:
        return True
    words = clean.split()
    if len(words) >= 2 and all(
        w.lower() in _LOC_PIPELINE_NOISE
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
    ):
        return True
    # All-lowercase multi-word phrase → common noun, not a proper location
    if len(words) >= 2 and clean == clean.lower():
        return True
    # Multi-word phrase starting with a lowercase word (adjective/article)
    # is almost never a proper location name.
    # E.g. "großen Stadiongelände", "deutschen Profivereine"
    if len(words) >= 2 and words[0][0].islower():
        return True
    return False


# ── PERSON noise ──────────────────────────────────────────────────────────

# Common first names (≤6 chars) ending in consonants that should NOT
# be suppressed by the short-name consonant heuristic (H10).
_PERSON_SHORT_NAME_WHITELIST: frozenset[str] = frozenset({
    # English
    "frank", "clark", "james", "david", "peter", "roger",
    "brian", "kevin", "robin", "jason", "grant", "jacob",
    "simon", "carol", "karen", "susan", "ellen", "helen",
    "janet", "sarah", "chris", "scott", "bruce", "ralph",
    # German
    "ernst", "heinz", "horst", "lukas", "niklas", "franz",
    "klaus", "armin", "bernd", "edgar", "erich", "eugen",
    "gerd", "kurt", "uwe", "lars", "sven", "hans",
    # French
    "alain", "henri", "louis", "denis", "yves",
    "jean", "marc", "paul",
    # Spanish
    "oscar", "jesus", "angel",
    # Dutch
    "ruben", "sander",
    # Portuguese
    "rui", "abel", "joel",
})




# ── German compound-word decomposition ────────────────────────────────────
# German creates compound nouns by concatenation (Haupt+Mieter → Hauptmieter).
# wordfreq dictionaries miss most compounds.  If a single word can be split
# into two known dictionary parts (with optional Fugen-element s/es/n/en/er/e)
# it is almost certainly a common noun, not a person name.

_FUGENLAUTE = det_cfg.GERMAN_FUGENLAUTE  # longest-first


def _is_german_compound_noun(word: str) -> bool:
    """Return True if *word* is a German compound of 2+ dictionary parts.

    Works by trying every split of the (lowercased, optionally inflection-
    stripped) form and checking left ∈ dict and right ∈ dict (with optional
    Fugen-element between them).

    Uses the German-only dictionary to avoid cross-language false positives
    (e.g. "Martin" → "mar" (ES) + "tin" (EN)).
    """
    _get_german_words()  # ensure dictionary is loaded into module global
    low = word.lower()
    # Try original + forms after stripping common inflectional suffixes
    forms: list[str] = [low]
    for suffix in ("s", "es", "en", "n", "er", "e", "em"):
        if low.endswith(suffix) and len(low) - len(suffix) >= 6:
            stripped = low[: -len(suffix)]
            if stripped not in forms:
                forms.append(stripped)
    for form in forms:
        if len(form) < 7:  # need at least 4 + 3
            continue
        for i in range(4, len(form) - 2):
            left = form[:i]
            if left not in _german_words:
                continue
            right = form[i:]
            if len(right) >= 3 and right in _german_words:
                return True
            # Try stripping a Fugen-element from the start of *right*
            for fg in _FUGENLAUTE:
                if right.startswith(fg):
                    rest = right[len(fg):]
                    if len(rest) >= 3 and rest in _german_words:
                        return True
    return False


def _is_person_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy PERSON false-positive."""
    clean = text.strip()
    low = clean.lower()
    if low in _PERSON_PIPELINE_NOISE:
        return True
    stripped = _re.sub(
        r"^(?:[Ll][ea]s?|[Dd][ue]s?|[Uu]n[e]?|[Ll]['']|[Dd]['']"  # FR
        r"|[Ee]l|[Ll]os|[Ll]as"  # ES
        r"|[Ii]l|[Gg]li|[Ll][oae]|[Uu]n[oa]?"  # IT
        r"|[Dd](?:er|ie|as|en|em|es)|[Ee]in[e]?"  # DE
        r"|[Hh]et|[Dd]e|[Ee]en"  # NL
        r"|[Oo]s?|[Aa]s?"  # PT
        r")\s+", "", clean)
    if stripped and stripped.lower() in _PERSON_PIPELINE_NOISE:
        return True
    if len(clean) <= 2:
        return True
    if clean.isdigit():
        return True
    if clean and clean[0].isdigit():
        return True
    if _re.fullmatch(r'[A-ZÀ-Ü](?:\.[A-ZÀ-Ü])+\.?', clean):
        return True
    if len(clean) <= 6 and clean[0].isupper() and clean[-1] in 'bcdfghjklmnpqrstvwxzç':
        # Bypass for known first names ending in consonants
        if clean.lower() not in _PERSON_SHORT_NAME_WHITELIST:
            return True
    words = clean.split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    if len(words) == 1 and clean.isupper():
        return True
    if len(words) >= 2 and all(
        w.lower() in _PERSON_PIPELINE_NOISE
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
    ):
        return True
    # German compound nouns misidentified as PERSON (e.g. Hauptmieters)
    if len(words) == 1 and len(clean) >= 8 and _is_german_compound_noun(clean):
        return True
    # All-lowercase multi-word phrase → common noun, not a person name
    if len(words) >= 2 and clean == clean.lower():
        return True
    # Multi-word phrase starting with a lowercase word (adjective/article)
    # is almost never a proper person name.
    # E.g. "notariell beurkundeten Gesellschafterbeschluss"
    if len(words) >= 2 and words[0][0].islower():
        return True
    return False


# ── ADDRESS number-only filter ────────────────────────────────────────────

_ADDR_ALPHA_RE = _re.compile(r"[A-Za-zÀ-ÿ]")
_ADDR_DIGIT_RE = _re.compile(r"\d")

# Pre-compiled word-boundary regex for mortgage/loan terms that
# disqualify an ADDRESS region.  Uses \b to avoid substring FPs
# (e.g. "Capital Street" no longer matches "capital").
_MORTGAGE_TERM_RE = _re.compile(
    r"\b(?:"
    # French
    r"hypoth[ée]caire|hypoth[èe]que|remboursable|remboursements?"
    r"|mensuell?e?s?|trimestriell?e?s?|annuell?e?s?"
    r"|[ée]ch[ée]ances?|echeances?"
    r"|capital|int[ée]r[êe]ts?|interets?"
    r"|emprunts?|pr[êe]ts?|prets?"
    r"|cr[ée]ancier|creancier|d[ée]biteur|debiteur"
    # English
    r"|mortgages?|repayments?|repayable"
    r"|monthly|quarterly|annually"
    r"|maturity|maturities"
    r"|principal|interests?"
    r"|loans?|lender|borrower|creditor|debtor"
    # German
    r"|hypotheken?|hypothekarisch"
    r"|r[üu]ckzahlung|rueckzahlung|tilgungen?"
    r"|monatlich|viertelj[äa]hrlich|vierteljaehrlich|j[äa]hrlich|jaehrlich"
    r"|f[äa]lligkeit|faelligkeit"
    r"|darlehen|kredite?"
    r"|gl[äa]ubiger|glaeubiger|schuldner"
    # Spanish
    r"|hipotecas?|hipotecari[oa]"
    r"|reembolsos?|reembolsable"
    r"|mensual(?:es)?|trimestral(?:es)?"
    r"|anual(?:es)?"
    r"|vencimientos?"
    r"|pr[ée]stamos?|prestamos?"
    r"|acreedore?s?|deudore?s?"
    # Italian
    r"|ipoteche?|ipotecari[oa]"
    r"|rimborsi?|rimborsabile"
    r"|mensil[ei]|trimestral[ei]"
    r"|annual[ei]"
    r"|scadenze?"
    r"|mutu[oi]|prestit[oi]"
    r"|creditor[ei]|debitor[ei]"
    # Dutch
    r"|hypotheek|hypotheken"
    r"|terugbetalingen?|aflossingen?"
    r"|maandelijks|driemaandelijks|kwartaal|jaarlijks"
    r"|vervaldatum"
    r"|leningen?"
    r"|schuldeiser|schuldenaar"
    # Portuguese
    r"|hipotec[áa]ri[oa]"
    r"|reembols[áa]vel|reembolsavel"
    r"|mensai?s?|trimestrais?"
    r"|anuais?"
    r"|vencimentos?"
    r"|empr[ée]stimos?|emprestimos?"
    r"|credore?s?|devedore?s?"
    r")\b",
    _re.IGNORECASE,
)


def _is_address_number_only(text: str) -> bool:
    """Return True if an ADDRESS region is structurally invalid.

    Real addresses always contain *both* alphabetic characters (street /
    city name) **and** at least one digit (street number, postal code,
    suite, etc.).
    """
    clean = text.strip()
    if not clean:
        return True
    has_alpha = _ADDR_ALPHA_RE.search(clean) is not None
    has_digit = _ADDR_DIGIT_RE.search(clean) is not None
    if not (has_alpha and has_digit):
        return True
    low = clean.lower()
    # REMOVED: substring matching caused false negatives on real addresses
    # containing words like "capital", "interest", etc.
    # Now uses word-boundary matching via compiled regex.
    if _MORTGAGE_TERM_RE.search(low):
        return True
    return False


# ── Structured type minimum digit counts ──────────────────────────────────

_STRUCTURED_MIN_DIGITS: dict[PIIType, int] = {
    PIIType.PHONE: 7,
    PIIType.SSN: 7,
    PIIType.DRIVER_LICENSE: 6,
}


# ── Phone-label stripping for ADDRESS regions ────────────────────────────

# These labels (and their multilingual counterparts) indicate a phone/fax
# line.  They should never be part of a detected ADDRESS region.
# Anchored to start-of-line, newline, OR whitespace so it also matches
# phone labels on the same visual line as the address (OCR text uses
# spaces between blocks on the same line, not newlines).
_PHONE_LABEL_RE = _re.compile(
    r"(?:^|\n|\s+)"
    r"(?:"
    r"Phone|Tel(?:e(?:phone|fon|fax))?|T[ée]l(?:[ée]ph(?:one)?)?|"
    r"T[ée]l[ée]c(?:opieur)?|Telex|Facs(?:imile)?|"
    r"Telec[óo]p(?:ia)?|"
    r"Mob(?:ile?)?|Cell(?:ulare)?|Celular|Fax|"
    r"Port(?:able)?|Fixe|Rufn(?:ummer|r)?|Handy|"
    r"Tel[ée]fono|Telefoon|Telefone"
    r")"
    r"\.?"                         # optional abbreviation dot (Tél.)
    r"(?:\s*(?:No\.?|Number|Num[ée]ro|#|N°))?"
    r"\s*[:.]?\s*"
    r"[\d\s\+\(\)\.\-]*$",
    _re.IGNORECASE | _re.MULTILINE,
)


def _strip_phone_labels_from_address(text: str) -> str:
    """Remove trailing/leading phone label lines from address text.

    Addresses merged from NER or label-value patterns sometimes absorb
    an adjacent "Tel: 555-1234" line.  This strips it and returns the
    cleaned address text.
    """
    cleaned = _PHONE_LABEL_RE.sub("", text).strip()
    return cleaned if cleaned else text


# ── Unified noise dispatcher ─────────────────────────────────────────────


def is_pipeline_noise(text: str, pii_type: PIIType) -> bool:
    """Unified entry point – returns True if *text* is noise for *pii_type*.

    Dispatches to the type-specific ``_is_<type>_pipeline_noise`` helpers.
    Callers that need only one check can still use the individual functions
    directly; this wrapper is a convenience for generic loops.
    """
    if pii_type == PIIType.ORG:
        return _is_org_pipeline_noise(text)
    if pii_type == PIIType.LOCATION:
        return _is_loc_pipeline_noise(text)
    if pii_type == PIIType.PERSON:
        return _is_person_pipeline_noise(text)
    if pii_type == PIIType.ADDRESS:
        return _is_address_number_only(text)
    return False
