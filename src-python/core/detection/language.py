"""Lightweight stop-word-based language detection for PII pipeline.

Detects: English (en), Spanish (es), French (fr), German (de),
Italian (it), Dutch (nl), Portuguese (pt).  Falls back to ``"en"``
for very short texts or languages outside the supported set.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Languages supported by the auto-switching NER backend.
SUPPORTED_LANGUAGES = ("en", "es", "fr", "de", "it", "nl", "pt")

# Model routing for auto mode
AUTO_MODEL_ENGLISH = "Isotonic/distilbert_finetuned_ai4privacy_v2"
AUTO_MODEL_MULTILINGUAL = "iiiorg/piiranha-v1-detect-personal-information"

_SAMPLE_SIZE = 2_000          # chars to sample
_MIN_WORDS = 20               # need this many tokens to judge
_THRESHOLD = 0.10             # 10 % stop-word ratio to claim a language

# ---------------------------------------------------------------------------
# Stop-word sets (top ~60 function words per language)
# ---------------------------------------------------------------------------

_STOP: dict[str, frozenset[str]] = {
    "en": frozenset({
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "her", "she",
        "or", "an", "will", "my", "one", "all", "would", "there", "their",
        "what", "so", "if", "about", "who", "which", "when", "can", "no",
        "just", "him", "know", "into", "your", "some", "could", "them",
        "than", "then", "its", "over", "also", "after", "how", "our",
        "well", "even", "because", "any", "these", "us", "out", "was",
        "were", "been", "being", "had", "has", "did", "are", "is", "am",
    }),
    "es": frozenset({
        "de", "la", "que", "el", "en", "y", "a", "los", "del", "se",
        "las", "por", "un", "para", "con", "no", "una", "su", "al", "lo",
        "como", "pero", "sus", "le", "ya", "o", "este", "entre", "cuando",
        "muy", "sin", "sobre", "me", "hasta", "hay", "donde", "quien",
        "desde", "todo", "nos", "durante", "todos", "uno", "les", "ni",
        "contra", "otros", "ese", "eso", "ante", "ellos", "esto", "antes",
        "algunos", "unos", "yo", "otro", "otras", "otra", "tanto", "esa",
        "estos", "esta", "fue", "son", "tiene", "ser", "han", "era",
    }),
    "fr": frozenset({
        "de", "la", "le", "et", "les", "des", "en", "un", "du", "une",
        "que", "est", "dans", "qui", "par", "pour", "au", "il", "sur",
        "ne", "se", "pas", "plus", "son", "ce", "avec", "ou", "mais",
        "sont", "sa", "aux", "ont", "ses", "cette", "comme", "nous",
        "tout", "aussi", "elle", "fait", "ces", "entre", "dont", "leur",
        "bien", "peut", "tous", "sans", "je", "lui", "donc", "encore",
        "avant", "depuis", "nos", "deux", "fois", "elle", "avait", "peut",
    }),
    "de": frozenset({
        "der", "die", "und", "in", "den", "von", "zu", "das", "mit",
        "sich", "des", "auf", "ist", "im", "dem", "nicht", "ein",
        "eine", "als", "auch", "es", "an", "werden", "aus", "er", "hat",
        "dass", "sie", "nach", "wird", "bei", "einer", "um", "am", "sind",
        "noch", "wie", "einem", "so", "zum", "aber", "ihr", "nur",
        "oder", "mir", "war", "mich", "gegen", "vom", "wenn", "durch",
        "dann", "unter", "sehr", "selbst", "schon", "hier", "bis", "alle",
        "diese", "mehr", "da", "wo", "kann", "haben", "sein",
    }),
    "it": frozenset({
        "di", "che", "la", "il", "un", "a", "per", "in", "una", "mi",
        "ma", "lo", "ha", "le", "si", "ho", "non", "con", "li", "da",
        "se", "no", "come", "io", "ci", "questo", "dei", "nel", "del",
        "al", "sono", "era", "gli", "suo", "anche", "alla", "dei",
        "tutto", "della", "fatto", "dal", "stata", "ancora", "dopo",
        "essere", "quella", "fare", "qui", "dove", "suo", "sua",
        "stato", "loro", "questa", "tra", "hai", "poi", "abbiamo",
    }),
    "nl": frozenset({
        "de", "het", "een", "van", "en", "in", "is", "dat", "op", "te",
        "zijn", "voor", "met", "die", "niet", "er", "aan", "ook", "als",
        "maar", "om", "bij", "dan", "nog", "naar", "heeft", "ze", "uit",
        "kan", "dit", "was", "worden", "al", "wel", "over", "door", "tot",
        "veel", "meer", "had", "haar", "wat", "zou", "hun", "geen", "werd",
        "wij", "heb", "moet", "ons", "dag", "twee", "zo", "alle", "hij",
    }),
    "pt": frozenset({
        "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
        "com", "uma", "os", "no", "se", "na", "por", "mais", "as",
        "dos", "como", "mas", "foi", "ao", "ele", "das", "tem", "seu",
        "sua", "ou", "ser", "quando", "muito", "nos", "já", "eu",
        "também", "só", "pelo", "pela", "até", "isso", "ela", "entre",
        "era", "depois", "sem", "mesmo", "aos", "ter", "seus", "quem",
        "nas", "me", "esse", "eles", "está", "você", "tinha", "foram",
        "essa", "num", "nem", "suas", "meu", "minha", "numa", "pelos",
    }),
}


def detect_language(text: str) -> str:
    """Return the ISO-639-1 code of the most-likely language.

    Uses stop-word frequency analysis on a sample of the text.
    Returns ``"en"`` as a safe default when the text is too short
    or no language reaches the threshold.
    """
    sample = text[:_SAMPLE_SIZE]
    words = [w.lower().strip(".,;:!?()[]{}\"'""''«»—–-") for w in sample.split()]
    words = [w for w in words if len(w) >= 2]

    if len(words) < _MIN_WORDS:
        return "en"  # too short to judge — default English

    n = len(words)
    best_lang = "en"
    best_ratio = 0.0

    for lang, stops in _STOP.items():
        hits = sum(1 for w in words if w in stops)
        ratio = hits / n
        if ratio > best_ratio:
            best_ratio = ratio
            best_lang = lang

    if best_ratio < _THRESHOLD:
        best_lang = "en"  # nothing matched well enough

    logger.info(
        "Language detection: %s (%.1f%% stop-word match, %d words sampled)",
        best_lang, best_ratio * 100, n,
    )
    return best_lang


def resolve_auto_model(text: str) -> tuple[str, str]:
    """Pick the best NER model for *text* when ``ner_backend == "auto"``.

    Returns ``(model_id, detected_language_code)``.
    """
    lang = detect_language(text)
    if lang == "en":
        return AUTO_MODEL_ENGLISH, lang
    else:
        return AUTO_MODEL_MULTILINGUAL, lang
