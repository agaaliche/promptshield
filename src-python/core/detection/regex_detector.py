"""Regex-based PII detector — Layer 1 of the hybrid pipeline.

Fast, high-precision detection of structured PII patterns:
SSN, email, phone, credit card, IBAN, dates, IP addresses,
driver's licenses, passport numbers, addresses, and names.

Includes validation functions (Luhn for credit cards, date-range
checks, IBAN modulo-97 check) and context-keyword proximity
boosting to reduce false positives and improve recall.

Design philosophy:
  - Maximise recall on structured/semi-structured data (the stuff regex
    is *good* at) so the slower NER/LLM layers have less work to do.
  - Keep precision high with validation gates, exclusion patterns, and
    a context-keyword confidence-boost system.
  - International coverage: US, FR, DE, ES, IT, UK, BE, NL, PT, plus
    generic EU patterns.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from models.schemas import PIIType
from core.detection.regex_patterns import (
    CONTEXT_KEYWORDS as _CONTEXT_KEYWORDS,
    CTX_WINDOW as _CTX_WINDOW,
    EXCLUDE_PATTERNS as _EXCLUDE_PATTERNS,
    PATTERNS as _PATTERNS,
    LABEL_NAME_PATTERNS as _LABEL_NAME_PATTERNS,
)


class RegexMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ═══════════════════════════════════════════════════════════════════════════
# Validation helpers
# ═══════════════════════════════════════════════════════════════════════════

def _luhn_check(number_str: str) -> bool:
    """Luhn algorithm — validates credit card numbers."""
    digits = [int(d) for d in number_str if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _valid_date(text: str) -> bool:
    """Check that a numeric date has plausible month (1-12) and day (1-31)."""
    parts = re.split(r"[/\-\.]", text)
    if len(parts) != 3:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False

    # Determine format: if first part > 31 it's YYYY-MM-DD
    if nums[0] > 31:
        _y, m, d = nums
    elif nums[2] > 31 or len(parts[2]) == 4:
        # DD/MM/YYYY or MM/DD/YYYY — try both
        if nums[0] > 12:
            d, m, _y = nums      # DD/MM/YYYY
        elif nums[1] > 12:
            m, d, _y = nums      # MM/DD/YYYY
        else:
            m, d, _y = nums      # Ambiguous — accept
    else:
        m, d, _y = nums

    return 1 <= m <= 12 and 1 <= d <= 31


def _iban_mod97(iban_str: str) -> bool:
    """Validate IBAN via ISO 7064 modulo-97 check."""
    clean = iban_str.replace(" ", "").replace("-", "").upper()
    if len(clean) < 15 or len(clean) > 34:
        return False
    if not clean[:2].isalpha() or not clean[2:4].isdigit():
        return False
    # Move first 4 chars to end, convert letters to numbers (A=10, B=11…)
    rearranged = clean[4:] + clean[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        else:
            numeric += str(ord(ch) - ord("A") + 10)
    return int(numeric) % 97 == 1


def _is_valid_french_ssn(text: str) -> bool:
    """Validate structure of a French numéro de sécurité sociale.

    Month field accepts:
      01-12  normal months
      20     Corsica (for historical numbers)
      30-42  foreign-born or special codes
      50+    overseas territories adjustments
      99     unknown month
    Only 00 is invalid.
    """
    digits = re.sub(r"\s", "", text)
    if len(digits) not in (13, 15):
        return False
    if digits[0] not in "12":
        return False
    month = int(digits[3:5])
    if month < 1 or month > 99:
        return False
    dept = int(digits[5:7])
    if dept < 1 or dept > 99:
        return False
    return True


def _is_valid_dutch_bsn(text: str) -> bool:
    """Validate a Dutch BSN using the 11-check algorithm.

    The BSN is 9 digits.  Multiply each digit by its position weight
    (9, 8, 7, 6, 5, 4, 3, 2, -1), sum results, and check divisibility
    by 11.
    """
    digits = re.sub(r"[\s.\-]", "", text)
    if len(digits) != 9 or not digits.isdigit():
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2, -1]
    total = sum(int(d) * w for d, w in zip(digits, weights))
    return total % 11 == 0 and total != 0


def _is_valid_portuguese_nif(text: str) -> bool:
    """Validate a Portuguese NIF (9 digits, mod-11 check digit)."""
    digits = re.sub(r"[\s.\-]", "", text)
    if len(digits) != 9 or not digits.isdigit():
        return False
    # First digit must be 1-3, 5, 6, 8, or 9
    if digits[0] not in "12356789":
        return False
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:8], weights))
    remainder = total % 11
    check = 0 if remainder < 2 else 11 - remainder
    return int(digits[8]) == check


def _is_valid_nhs_number(text: str) -> bool:
    """Validate a UK NHS number (10 digits, modulus-11 check digit).

    The check digit is in position 10. Weights are 10,9,8,...,2 for
    positions 1-9; remainder = sum mod 11; check = 11 - remainder;
    if check==11 it becomes 0; if check==10 the number is invalid.
    """
    digits = re.sub(r"[\s.\-]", "", text)
    if len(digits) != 10 or not digits.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], range(10, 1, -1)))
    remainder = total % 11
    check = 11 - remainder
    if check == 11:
        check = 0
    if check == 10:
        return False  # invalid
    return int(digits[9]) == check


def _is_valid_bic(text: str) -> bool:
    """Basic BIC/SWIFT structural validation.

    8 or 11 chars: 4 bank code + 2 country ISO + 2 location + optional 3 branch.
    Country code must be a valid ISO 3166-1 alpha-2 code (subset of common ones).
    """
    clean = text.strip().upper()
    if len(clean) not in (8, 11):
        return False
    if not clean[:4].isalpha():
        return False
    country = clean[4:6]
    # Reject obviously non-country codes
    _valid_countries = {
        "AD", "AE", "AT", "AU", "BE", "BG", "BH", "BR", "CA", "CH", "CL",
        "CN", "CO", "CY", "CZ", "DE", "DK", "EE", "EG", "ES", "FI", "FR",
        "GB", "GR", "HK", "HR", "HU", "ID", "IE", "IL", "IN", "IS", "IT",
        "JP", "KR", "KW", "LB", "LI", "LT", "LU", "LV", "MA", "MC", "MT",
        "MX", "MY", "NL", "NO", "NZ", "PE", "PH", "PL", "PT", "QA", "RO",
        "RS", "RU", "SA", "SE", "SG", "SI", "SK", "TH", "TR", "TW", "UA",
        "US", "UY", "VN", "ZA",
    }
    if country not in _valid_countries:
        return False
    return True


def _is_valid_italian_piva(text: str) -> bool:
    """Validate an Italian Partita IVA (11 digits, Luhn-like check)."""
    digits = re.sub(r"[\s.\-]", "", text)
    if len(digits) != 11 or not digits.isdigit():
        return False
    total = 0
    for i, d in enumerate(int(c) for c in digits):
        if i % 2 == 0:
            total += d
        else:
            doubled = d * 2
            total += doubled // 10 + doubled % 10
    return total % 10 == 0


def _is_valid_portuguese_niss(text: str) -> bool:
    """Validate a Portuguese NISS (11 digits, check digit algorithm).

    The NISS uses a weighted modulo-97 check.  Weights cycle through
    [29, 23, 19, 17, 13, 11, 7, 5, 3, 2] for the first 10 digits;
    the 11th digit is the check digit such that the weighted sum mod 10
    gives 0.  Reject obvious non-NISS patterns like all-same digits.
    """
    digits = re.sub(r"[\s.\-]", "", text)
    if len(digits) != 11 or not digits.isdigit():
        return False
    # Reject trivially invalid: all same digit (e.g. 11111111111)
    if len(set(digits)) == 1:
        return False
    weights = [29, 23, 19, 17, 13, 11, 7, 5, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits[:10], weights))
    remainder = total % 10
    check = (10 - remainder) % 10
    return int(digits[10]) == check


# BIC/SWIFT false-positive word list — common English words that
# happen to match the 8-char BIC structure with valid country codes.
_BIC_FP_WORDS: frozenset[str] = frozenset({
    "ABSTRACT", "ACHIEVED", "APPROACH", "ATTACHED",
    "BENEDEIT", "BENEFITS", "BRIGHTLY",
    "CHAPTERS", "CLOSURES", "COHERENT", "COMBINED",
    "CONCLUDE", "CONFLICT", "CONNECTS", "CONSIDER",
    "CONTENTS", "CONTRACT", "CONTROLS", "CREATION",
    "CREDITED", "CULTURES", "CUSTOMER", "DECEMBER",
    "DEFEATED", "DEPICTED", "DETAILED", "DISTINCT",
    "DOCTRINE", "DOCUMENT", "DOMESTIC",
    "DESCRIPT", "ELECTION", "ENTITLED", "ESTIMATE",
    "EVALUATE", "EVENTUAL", "EVALUATE", "EXPLORED",
    "FINISHED", "FORMERLY", "FRACTION",
    "FUNCTION", "GATHERED", "GENERATE", "GRATEFUL",
    "GRAPHICS", "GREATEST", "GUIDANCE",
    "HAPPENED", "HISTORIC", "INCIDENT", "INCLUDES",
    "INCREASE", "INDUSTRY", "INFINITE", "INFORMED",
    "INHERITS", "INITIATE", "INSPIRED", "INSTANCE",
    "INTEGRAL", "INTERACT", "INTEREST", "INTERNAL",
    "MULTIPLE", "NATIONAL", "NOTIFIED",
    "OBTAINED", "OCCURRED", "OFFICIAL", "OPERATED",
    "OPTIONAL", "OUTLINED", "OVERHEAD", "GATHERED",
    "PARALLEL", "PATIENTS", "PERFORMS", "PERIODIC",
    "PETITION", "PLATFORM", "PLEASURE", "POLITICS",
    "POSITIVE", "POSSIBLE", "PRACTICE", "PRECIOUS",
    "PRESENCE", "PRESERVE", "PREVIOUS", "PRINCESS",
    "PRIORITY", "PROBABLE", "PRODUCED", "PRODUCTS",
    "PROMOTED", "PROPERLY", "PROPOSAL", "PROPOSED",
    "COMBINED", "PROSPECT", "PROTOCOL", "PROVIDED",
    "PROVIDER", "PROVINCE", "PURCHASE",
    "REACTION", "RECEIVED", "RECENTLY", "RECORDED",
    "REFLECTS", "REGIONAL", "REGISTER", "REJECTED",
    "RELATION", "RELEASED", "REMAINED", "REMEMBER",
    "REPEATED", "REPLACED", "REPORTED", "REQUIRED",
    "RESEARCH", "RESERVED", "RESOLVED", "RESOURCE",
    "RESPONSE", "RESULTED", "RETAINED", "RETURNED",
    "REVIEWED", "REVISION", "SEARCHED",
    "SECTIONS", "SELECTED", "SENTENCE", "SEQUENCE",
    "SETTINGS", "SITUATED", "SOLUTION", "SPECIFIC",
    "STANDARD", "STRATEGY", "STRENGTH", "STRONGLY",
    "SUBJECTS", "SUPPLIED", "SUPPORTS", "SUPPOSED",
    "TOGETHER", "TRANSFER", "TREASURE", "UNLISTED",
    "UPLOADED", "UTILISED", "UTILIZES", "VERIFIED",
    "VETERANS", "VIOLATED", "INTENDED",
})


# ═══════════════════════════════════════════════════════════════════════════
# Context keyword proximity boost
# ═══════════════════════════════════════════════════════════════════════════

# Phone-specific labels that indicate a phone/fax line.
# Used for bidirectional proximity check (before AND after the match).
_PHONE_LABEL_KEYWORDS: frozenset[str] = frozenset({
    "phone", "tel", "tél", "téléphone", "telephone",
    "mobile", "mob", "cell", "cellulare", "celular",
    "fax", "portable", "port", "fixe",
    "rufnummer", "rufnr", "telefon", "handy", "mobil",
    "teléfono", "telefono",
    "télécopieur", "telecopieur", "téléc", "telec", "telex",
    "telefax", "facsimile", "facs", "telecópia", "telecopia",
    "téléph", "teleph", "telecóp", "telecop",
    "telefoon", "telefone",  # Dutch / Portuguese
})

# Penalty applied to PHONE matches with no nearby label keyword.
# This pushes bare numbers (base 0.55) below the confidence threshold
# while numbers already boosted by proximity (+0.25) are unaffected.
_PHONE_NO_LABEL_PENALTY = 0.15


# Pre-compile word-boundary regexes for context keyword matching.
# Using \b prevents "nom" matching inside "economy" or "port" inside "report".
def _compile_kw_patterns(
    kw_dict: dict[PIIType, list[str]],
) -> dict[PIIType, re.Pattern]:
    """Build one combined regex per PIIType from keyword lists."""
    result: dict[PIIType, re.Pattern] = {}
    for pii_type, kwlist in kw_dict.items():
        # Sort by length (longest first) so multi-word phrases match before
        # their shorter sub-strings.
        sorted_kws = sorted(kwlist, key=len, reverse=True)
        alternatives = "|".join(re.escape(kw) for kw in sorted_kws)
        result[pii_type] = re.compile(rf"(?:^|(?<=\W))(?:{alternatives})(?:$|(?=\W))", re.IGNORECASE)
    return result


_COMPILED_CTX_KW: dict[PIIType, re.Pattern] = _compile_kw_patterns(_CONTEXT_KEYWORDS)
_COMPILED_PHONE_LABEL_RE: re.Pattern = re.compile(
    r"(?:^|(?<=\W))(?:" + "|".join(
        re.escape(kw) for kw in sorted(_PHONE_LABEL_KEYWORDS, key=len, reverse=True)
    ) + r")(?:$|(?=\W))",
    re.IGNORECASE,
)


def _context_boost(text: str, match_start: int, pii_type: PIIType,
                   match_end: int | None = None) -> float:
    """Return a confidence adjustment for context keyword proximity.

    For PHONE type, uses bidirectional search (before + after) and applies
    a penalty (-0.15) when no label is found, so that bare digit sequences
    without any "Tel:", "Phone:", etc. nearby are penalised.

    For all other types, returns +0.25 if a keyword is nearby, else 0.0.

    Uses word-boundary-aware matching to prevent false boosts from
    sub-string hits (e.g. "nom" inside "economy").
    """
    ctx_re = _COMPILED_CTX_KW.get(pii_type)
    if not ctx_re:
        return 0.0

    # Look at the text window BEFORE the match
    window_start = max(0, match_start - _CTX_WINDOW)
    before = text[window_start:match_start]

    if ctx_re.search(before):
        return 0.25

    # For PHONE, also check phone-specific labels in the before-window
    # (covers abbreviations like "Port.", "Mob." that may only be in
    # _PHONE_LABEL_KEYWORDS and not in the broader CONTEXT_KEYWORDS).
    if pii_type == PIIType.PHONE:
        if _COMPILED_PHONE_LABEL_RE.search(before):
            return 0.25

    # For PHONE, also look AFTER the match (e.g. "418.368.3700 (tel)")
    if pii_type == PIIType.PHONE and match_end is not None:
        window_end = min(len(text), match_end + _CTX_WINDOW)
        after = text[match_end:window_end]
        if _COMPILED_PHONE_LABEL_RE.search(after):
            return 0.25
        # No label found anywhere near this phone number → penalise
        return -_PHONE_NO_LABEL_PENALTY

    return 0.0


def _in_excluded_context(text: str, match_start: int, match_end: int) -> bool:
    """Return True if the match falls inside a known non-PII context."""
    window_start = max(0, match_start - 30)
    window_end = min(len(text), match_end + 10)
    window = text[window_start:window_end]

    for pat in _EXCLUDE_PATTERNS:
        m = pat.search(window)
        if m:
            abs_start = window_start + m.start()
            abs_end = window_start + m.end()
            # Only exclude when the exclusion pattern fully contains
            # the candidate match — prevents partial sub-matches inside
            # a longer PII span from triggering false exclusions
            # (e.g. "85.05" inside "85.05.15-123.45").
            if abs_start <= match_start and abs_end >= match_end:
                return True
    return False


# Compile standalone patterns once at import time
_COMPILED_PATTERNS: list[tuple[re.Pattern, PIIType, float, frozenset[str] | None]] = [
    (re.compile(pattern, flags), pii_type, conf, langs)
    for pattern, pii_type, conf, flags, langs in _PATTERNS
]

# ---------------------------------------------------------------------------
# Custom patterns — user-defined regexes loaded from persistence
# ---------------------------------------------------------------------------

# Compiled custom patterns: (pattern, pii_type, confidence, case_sensitive, pattern_id, pattern_name)
_CUSTOM_PATTERNS: list[tuple[re.Pattern, PIIType, float, str, str]] = []
_CUSTOM_PATTERNS_LOADED: bool = False


def _load_custom_patterns() -> None:
    """Load and compile custom patterns from disk."""
    global _CUSTOM_PATTERNS, _CUSTOM_PATTERNS_LOADED
    
    try:
        from api.deps import get_store
        store = get_store()
        patterns = store.load_custom_patterns()
    except Exception:
        # During startup or tests, store may not be available
        _CUSTOM_PATTERNS = []
        _CUSTOM_PATTERNS_LOADED = True
        return
    
    compiled: list[tuple[re.Pattern, PIIType, float, str, str]] = []
    
    for p in patterns:
        if not p.get("enabled", True):
            continue
        
        pattern_str = p.get("pattern") or p.get("_generated_pattern")
        if not pattern_str:
            continue
        
        try:
            flags = 0 if p.get("case_sensitive", False) else re.IGNORECASE
            compiled_re = re.compile(pattern_str, flags)
            
            # Map pii_type string to PIIType enum
            pii_type_str = p.get("pii_type", "CUSTOM")
            try:
                pii_type = PIIType(pii_type_str)
            except ValueError:
                pii_type = PIIType.CUSTOM
            
            compiled.append((
                compiled_re,
                pii_type,
                p.get("confidence", 0.85),
                p.get("id", ""),
                p.get("name", "Custom"),
            ))
        except re.error:
            # Skip invalid patterns
            continue
    
    _CUSTOM_PATTERNS = compiled
    _CUSTOM_PATTERNS_LOADED = True


def reload_custom_patterns() -> None:
    """Reload custom patterns from disk. Called when patterns are saved."""
    global _CUSTOM_PATTERNS_LOADED
    _CUSTOM_PATTERNS_LOADED = False
    _load_custom_patterns()


def get_custom_pattern_count() -> int:
    """Return the number of enabled custom patterns."""
    if not _CUSTOM_PATTERNS_LOADED:
        _load_custom_patterns()
    return len(_CUSTOM_PATTERNS)

def _validate_match(text: str, matched_text: str, pii_type: PIIType,
                    match_start: int = 0) -> float:
    """
    Return an adjusted confidence (or 0.0 to reject) based on content
    validation of the matched text.  Returns -1.0 for "no adjustment".
    """
    # Credit card: Luhn check
    if pii_type == PIIType.CREDIT_CARD:
        if not _luhn_check(matched_text):
            return 0.0

    # Date: validate month/day ranges
    if pii_type == PIIType.DATE:
        if re.match(r"^\d{1,4}[/\-\.]\d{1,2}[/\-\.]\d{1,4}$", matched_text):
            if not _valid_date(matched_text):
                return 0.0

    # IBAN: modulo-97 check — only for actual IBAN format (CC## ...)
    # Skip validation for sort code, routing number, and account number patterns
    if pii_type == PIIType.IBAN:
        clean_iban = matched_text.replace(" ", "").replace("-", "").upper()
        if len(clean_iban) >= 15 and clean_iban[:2].isalpha() and clean_iban[2:4].isdigit():
            if not _iban_mod97(matched_text):
                return 0.0

    # French SSN: structural validation
    if pii_type == PIIType.SSN:
        ssn_digits = re.sub(r"\s", "", matched_text)
        if len(ssn_digits) in (13, 15) and ssn_digits[0] in "12":
            if not _is_valid_french_ssn(matched_text):
                return 0.0

    # Dutch BSN / Portuguese NIF: only validate bare 9-digit numbers.
    # Do NOT apply to US SSN (has hyphens/spaces), Spanish DNI (has letter),
    # or other formatted SSN patterns.
    if pii_type == PIIType.SSN:
        clean = matched_text.strip()
        if re.match(r"^\d{9}$", clean):
            is_valid_bsn = _is_valid_dutch_bsn(clean)
            is_valid_nif = (
                clean[0] in "12356789" and _is_valid_portuguese_nif(clean)
            )
            if not is_valid_bsn and not is_valid_nif:
                return 0.0

    # NHS number: 10-digit numbers — validate mod-11 check digit
    if pii_type == PIIType.SSN:
        clean = matched_text.strip()
        digits_only = re.sub(r"\s", "", clean)
        if re.match(r"^\d{10}$", digits_only):
            if not _is_valid_nhs_number(digits_only):
                return 0.0

    # BIC/SWIFT: structural validation + English word filter
    if pii_type == PIIType.CUSTOM:
        clean = matched_text.strip().upper()
        if re.match(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$", clean):
            if not _is_valid_bic(clean):
                return 0.0
            # Reject common English words that pass BIC structure
            if clean in _BIC_FP_WORDS:
                return 0.0

    # Italian Partita IVA: 11-digit validation
    if pii_type == PIIType.CUSTOM:
        clean = matched_text.strip()
        if re.match(r"^\d{11}$", clean):
            if not _is_valid_italian_piva(clean):
                return 0.0

    # Portuguese NISS: 11-digit SSN validation
    if pii_type == PIIType.SSN:
        clean = matched_text.strip()
        if re.match(r"^\d{11}$", clean):
            if not _is_valid_portuguese_niss(clean):
                return 0.0

    return -1.0  # no adjustment


def detect_regex(text: str, allowed_types: list[str] | None = None,
                 detection_language: str | None = None) -> list[RegexMatch]:
    """
    Scan text with all regex patterns and return matches.

    Args:
        text: The text to scan.
        allowed_types: Optional list of PIIType values to include (e.g. ["EMAIL", "SSN"]).
                       If None, all types are included.
        detection_language: ISO 639-1 language code (e.g. "fr", "en").
                           When set, only patterns tagged for that language (or
                           tagged with None = all languages) are executed.
                           When None or "auto", all patterns run.

    Applies validation, context-keyword boosting, and exclusion
    filtering to reduce false positives. Returns non-overlapping
    matches sorted by position.
    """
    _allowed = set(allowed_types) if allowed_types else None
    # Normalise language filter
    _lang = detection_language if detection_language and detection_language != "auto" else None
    all_matches: list[RegexMatch] = []

    for compiled_re, pii_type, base_confidence, langs in _COMPILED_PATTERNS:
        if _allowed and pii_type.value not in _allowed:
            continue
        # Language filter: skip pattern if it doesn't match the document lang
        if _lang and langs is not None and _lang not in langs:
            continue
        for m in compiled_re.finditer(text):
            matched_text = m.group()

            # ── Validation gate ──
            adjusted = _validate_match(text, matched_text, pii_type, m.start())
            if adjusted == 0.0:
                continue
            confidence = base_confidence if adjusted < 0 else adjusted

            # ── Exclusion gate (page numbers, section refs, etc.) ──
            if _in_excluded_context(text, m.start(), m.end()):
                continue

            # ── Context keyword proximity boost ──
            boost = _context_boost(text, m.start(), pii_type, m.end())
            confidence = min(1.0, confidence + boost)

            all_matches.append(RegexMatch(
                start=m.start(),
                end=m.end(),
                text=matched_text,
                pii_type=pii_type,
                confidence=confidence,
            ))

    # ── Label-value patterns (capture-group extraction) ──
    for compiled_re, pii_type, base_confidence, langs in _LABEL_NAME_PATTERNS:
        if _allowed and pii_type.value not in _allowed:
            continue
        if _lang and langs is not None and _lang not in langs:
            continue
        for m in compiled_re.finditer(text):
            value_text = m.group(1)
            if not value_text or len(value_text.strip()) < 3:
                continue

            name_start = m.start(1)
            name_end = m.end(1)

            # Validate extracted value
            adjusted = _validate_match(text, value_text, pii_type, name_start)
            if adjusted == 0.0:
                continue

            boost = _context_boost(text, name_start, pii_type, name_end)
            confidence = min(1.0, base_confidence + boost)

            all_matches.append(RegexMatch(
                start=name_start,
                end=name_end,
                text=value_text,
                pii_type=pii_type,
                confidence=confidence,
            ))

    # ── Custom user-defined patterns ──
    from core.config import config as _cfg
    if _cfg.custom_patterns_enabled:
        if not _CUSTOM_PATTERNS_LOADED:
            _load_custom_patterns()

        for compiled_re, pii_type, base_confidence, pattern_id, pattern_name in _CUSTOM_PATTERNS:
            if _allowed and pii_type.value not in _allowed:
                continue
            for m in compiled_re.finditer(text):
                matched_text = m.group()

                # Skip empty or whitespace-only matches
                if not matched_text or not matched_text.strip():
                    continue

                # Skip if in excluded context
                if _in_excluded_context(text, m.start(), m.end()):
                    continue

                all_matches.append(RegexMatch(
                    start=m.start(),
                    end=m.end(),
                    text=matched_text,
                    pii_type=pii_type,
                    confidence=base_confidence,
                ))

    # Sort by start position, remove overlaps (keep higher confidence)
    # Special handling for containment: prefer longer spans when one
    # match is fully inside another.
    all_matches.sort(key=lambda x: (x.start, -x.confidence))
    filtered: list[RegexMatch] = []

    for match in all_matches:
        if not filtered:
            filtered.append(match)
            continue

        last = filtered[-1]
        if match.start < last.end:
            # Overlap detected
            last_len = last.end - last.start
            match_len = match.end - match.start

            # Containment: if new match is fully inside existing, skip it
            # unless it has much higher confidence (>0.20 diff)
            if match.start >= last.start and match.end <= last.end:
                if match.confidence > last.confidence + 0.20:
                    filtered[-1] = match
                # else: skip — existing longer match is better
                continue

            # Containment: existing is fully inside new match
            if last.start >= match.start and last.end <= match.end:
                if last.confidence <= match.confidence + 0.20:
                    filtered[-1] = match
                continue

            # Partial overlap — keep the one with higher confidence
            if match.confidence > last.confidence:
                filtered[-1] = match
            elif match.confidence == last.confidence and match_len > last_len:
                filtered[-1] = match
        else:
            filtered.append(match)

    return filtered
