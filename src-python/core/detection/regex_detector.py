"""Regex-based PII detector — Layer 1 of the hybrid pipeline.

Fast, high-precision detection of structured PII patterns:
SSN, email, phone, credit card, IBAN, dates, IP addresses,
plus name patterns (title + capitalized words) as NER fallback.

Includes validation functions (Luhn for credit cards, date-range
checks) and context-keyword proximity boosting to reduce false
positives and improve recall.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from models.schemas import PIIType


class RegexMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

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
    parts = re.split(r"[/\-]", text)
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
        m, d, _y = nums
    else:
        # Ambiguous — accept if month/day plausible either way
        m, d, _y = nums

    return 1 <= m <= 12 and 1 <= d <= 31


# ---------------------------------------------------------------------------
# Context keyword proximity boost
# ---------------------------------------------------------------------------

# Keywords that, when appearing within _CTX_WINDOW chars BEFORE a match,
# significantly increase the likelihood that it's real PII.
_CONTEXT_KEYWORDS: dict[PIIType, list[str]] = {
    PIIType.SSN: ["ssn", "social security", "social sec", "tax id", "tin"],
    PIIType.PHONE: ["phone", "tel", "mobile", "cell", "fax", "call", "contact"],
    PIIType.EMAIL: ["email", "e-mail", "mail"],
    PIIType.CREDIT_CARD: ["card", "credit", "debit", "visa", "mastercard", "amex",
                           "payment", "account"],
    PIIType.IBAN: ["iban", "bank", "account", "swift", "bic"],
    PIIType.DATE: ["born", "birth", "dob", "date of birth", "expires", "expiry",
                    "issued", "valid"],
    PIIType.PERSON: ["name", "patient", "client", "applicant", "employee",
                      "mr", "mrs", "ms", "dr", "prof", "sir", "madam",
                      "first name", "last name", "full name", "surname"],
    PIIType.ADDRESS: ["address", "street", "city", "state", "zip", "postal",
                       "residence", "home", "mailing"],
    PIIType.PASSPORT: ["passport"],
    PIIType.DRIVER_LICENSE: ["driver", "license", "licence", "dl", "driving"],
    PIIType.IP_ADDRESS: ["ip", "address"],
}

_CTX_WINDOW = 80  # characters to look back for context keywords

def _context_boost(text: str, match_start: int, pii_type: PIIType) -> float:
    """Return a confidence boost (0.0 – 0.20) if context keywords are nearby."""
    keywords = _CONTEXT_KEYWORDS.get(pii_type)
    if not keywords:
        return 0.0

    # Look at the text window before the match
    window_start = max(0, match_start - _CTX_WINDOW)
    context = text[window_start:match_start].lower()

    for kw in keywords:
        if kw in context:
            return 0.20
    return 0.0


# ---------------------------------------------------------------------------
# Exclusion / negative patterns  (common false positives)
# ---------------------------------------------------------------------------

# Strings that commonly produce false positives — skip matches that
# are exactly one of these or fall inside a known non-PII context.
_EXCLUDE_PATTERNS: list[re.Pattern] = [
    # Page numbers: "Page 3", "page 12 of 20", "p. 5"
    re.compile(r"\bpage\s+\d+", re.IGNORECASE),
    re.compile(r"\bp\.\s*\d+", re.IGNORECASE),
    # Section / figure / table references: "Section 3.2", "Fig. 5", "Table 12"
    re.compile(r"\b(?:section|sec|figure|fig|table|tab|chapter|ch|item|no|#)\s*\.?\s*\d+", re.IGNORECASE),
    # Version numbers: "v1.2.3", "version 2.0"
    re.compile(r"\bv(?:ersion)?\s*\d+(?:\.\d+)+", re.IGNORECASE),
    # Percentages: "42%", "3.5%"
    re.compile(r"\b\d+(?:\.\d+)?%"),
    # Currency amounts: "$100", "€50.00", "£1,234"
    re.compile(r"[$€£¥]\s*\d"),
    re.compile(r"\b\d[\d,]*\.\d{2}\b"),  # Amounts like 1,234.56
]


def _in_excluded_context(text: str, match_start: int, match_end: int) -> bool:
    """Return True if the match falls inside a known non-PII context."""
    # Check a wider window around the match
    window_start = max(0, match_start - 30)
    window_end = min(len(text), match_end + 10)
    window = text[window_start:window_end]

    for pat in _EXCLUDE_PATTERNS:
        m = pat.search(window)
        if m:
            # If the exclusion pattern overlaps our match, skip it
            abs_start = window_start + m.start()
            abs_end = window_start + m.end()
            if abs_start <= match_start and abs_end >= match_end:
                return True
            # Also check if match is within the exclusion span
            if abs_start < match_end and abs_end > match_start:
                return True
    return False


# ---------------------------------------------------------------------------
# Pattern definitions (tuned for precision)
# ---------------------------------------------------------------------------

# Flag constants
_NOFLAGS = 0
_IC = re.IGNORECASE

# Each tuple: (pattern, PIIType, base_confidence, re_flags)
_PATTERNS: list[tuple[str, PIIType, float, int]] = [
    # ── Social Security Number (US) ──
    # Only dashed format; low base confidence — needs keyword context
    # ("SSN", "social security") to survive the threshold.
    (r"\b\d{3}-\d{2}-\d{4}\b", PIIType.SSN, 0.50, _NOFLAGS),

    # ── Email ──  (very high precision — almost never a false positive)
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", PIIType.EMAIL, 0.98, _NOFLAGS),

    # ── Phone ──
    # ONLY match phones that have parentheses around the area code.
    # Plain "123-456-7890" matches too many reference numbers in documents.
    (r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}", PIIType.PHONE, 0.92, _NOFLAGS),
    # International with "+" prefix — high precision
    (r"\+\d{1,3}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}", PIIType.PHONE, 0.88, _NOFLAGS),
    # Toll-free: 1-800-xxx-xxxx, 1-866-xxx-xxxx etc.
    (r"\b1[-.]8(?:00|44|55|66|77|88)\b[-.\s]?\d{3}[-.\s]\d{4}\b", PIIType.PHONE, 0.90, _NOFLAGS),

    # ── Credit card ──
    # 16 digits with Luhn validation applied post-match.
    # Only match when separated by dashes or spaces (not bare 16 digits).
    (r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b", PIIType.CREDIT_CARD, 0.90, _NOFLAGS),
    # Amex (15 digits, starts with 34 or 37)
    (r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b", PIIType.CREDIT_CARD, 0.90, _NOFLAGS),

    # ── IBAN — REMOVED ──
    # The pattern [A-Z]{2}\d{2}... matches too many document reference
    # codes and filing numbers in financial/legal PDFs.

    # ── Date formats — context-only ──
    # Very low base confidence; only shown when near "DOB", "birth", "expiry" etc.
    (r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{4}\b", PIIType.DATE, 0.35, _NOFLAGS),
    (r"\b\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\b", PIIType.DATE, 0.35, _NOFLAGS),
    (
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        PIIType.DATE, 0.40, _IC,
    ),

    # ── IP Address ──
    (
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        PIIType.IP_ADDRESS, 0.85, _NOFLAGS,
    ),

    # ── Driver's license (US) — very specific format only ──
    (r"\b[A-Z]\d{3}-\d{4}-\d{4}\b", PIIType.DRIVER_LICENSE, 0.75, _NOFLAGS),

    # ── Address — REMOVED ──
    # Street address patterns match too many things in documents.
    # Addresses are better caught by NER (GPE/LOC) or LLM.

    # ── Name patterns (regex, high precision) ──
    # Title + Name:  "Mr. John Smith", "Dr. Jane Doe-Peters"
    (
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Sir|Madam|Mme|Herr|Frau)"
        r"\.?[ \t]+[A-Z][a-z]{1,20}(?:[ \t]+[A-Z][a-z]{1,20}){1,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS,
    ),
]

# Label-value name patterns — handled separately because we want to
# return only the name portion, not the label.  Each pattern MUST
# have exactly one capture group around the name text.
_LABEL_NAME_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    # "Name: John Smith", "Full Name: Jane Doe"
    (re.compile(
        r"(?:(?:First|Last|Full|Middle|Sur|Family|Given)[ \t]*[Nn]ame|[Nn]ame)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})"
    ), PIIType.PERSON, 0.85),
    # "Patient: John Smith", "Client: Jane Doe"
    (re.compile(
        r"(?:Patient|Client|Applicant|Employee|Insured|Beneficiary|Claimant)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85),
    # "Passport: AB1234567", "Passport No: CD7654321"
    (re.compile(
        r"(?:Passport)[ \t]*(?:No\.?|Number|#)?[ \t]*[:]?[ \t]*([A-Z]{2}\d{7})",
        re.IGNORECASE,
    ), PIIType.PASSPORT, 0.85),
]

# Compile patterns — each pattern now carries its own flags
_COMPILED_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    (re.compile(pattern, flags), pii_type, conf)
    for pattern, pii_type, conf, flags in _PATTERNS
]


# ---------------------------------------------------------------------------
# Post-match validators
# ---------------------------------------------------------------------------

def _validate_match(text: str, matched_text: str, pii_type: PIIType) -> float:
    """
    Return an adjusted confidence (or 0.0 to reject) based on content
    validation of the matched text.
    """
    # Credit card: Luhn check
    if pii_type == PIIType.CREDIT_CARD:
        if not _luhn_check(matched_text):
            return 0.0  # Not a valid card number — reject

    # Date: validate month/day ranges
    if pii_type == PIIType.DATE:
        # Only validate numeric-format dates
        if re.match(r"^\d{1,4}[/\-]\d{1,2}[/\-]\d{1,4}$", matched_text):
            if not _valid_date(matched_text):
                return 0.0  # Impossible date like 15/42/2024

    return -1.0  # -1 means "no adjustment, keep original confidence"


def detect_regex(text: str) -> list[RegexMatch]:
    """
    Scan text with all regex patterns and return matches.

    Applies validation, context-keyword boosting, and exclusion
    filtering to reduce false positives. Returns non-overlapping
    matches sorted by position.
    """
    all_matches: list[RegexMatch] = []

    for compiled_re, pii_type, base_confidence in _COMPILED_PATTERNS:
        for m in compiled_re.finditer(text):
            matched_text = m.group()

            # ── Validation gate ──
            adjusted = _validate_match(text, matched_text, pii_type)
            if adjusted == 0.0:
                continue  # Rejected by validator
            confidence = base_confidence if adjusted < 0 else adjusted

            # ── Exclusion gate (page numbers, section refs, etc.) ──
            if _in_excluded_context(text, m.start(), m.end()):
                continue

            # ── Context keyword proximity boost ──
            boost = _context_boost(text, m.start(), pii_type)
            confidence = min(1.0, confidence + boost)

            all_matches.append(RegexMatch(
                start=m.start(),
                end=m.end(),
                text=matched_text,
                pii_type=pii_type,
                confidence=confidence,
            ))

    # ── Label-value name patterns (capture-group extraction) ──
    for compiled_re, pii_type, base_confidence in _LABEL_NAME_PATTERNS:
        for m in compiled_re.finditer(text):
            name_text = m.group(1)
            if not name_text or len(name_text.strip()) < 3:
                continue

            # Offset of the captured name within the full text
            name_start = m.start(1)
            name_end = m.end(1)

            boost = _context_boost(text, name_start, pii_type)
            confidence = min(1.0, base_confidence + boost)

            all_matches.append(RegexMatch(
                start=name_start,
                end=name_end,
                text=name_text,
                pii_type=pii_type,
                confidence=confidence,
            ))

    # Sort by start position, remove overlaps (keep higher confidence)
    all_matches.sort(key=lambda x: (x.start, -x.confidence))
    filtered: list[RegexMatch] = []
    last_end = -1

    for match in all_matches:
        if match.start >= last_end:
            filtered.append(match)
            last_end = match.end
        else:
            # Overlap — keep existing (already highest confidence due to sort)
            pass

    return filtered
