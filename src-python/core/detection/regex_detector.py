"""Regex-based PII detector — Layer 1 of the hybrid pipeline.

Fast, high-precision detection of structured PII patterns:
SSN, email, phone, credit card, IBAN, dates, IP addresses.
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
# Pattern definitions
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, PIIType, float]] = [
    # Social Security Number (US)
    (r"\b\d{3}-\d{2}-\d{4}\b", PIIType.SSN, 0.95),
    # SSN without dashes
    (r"\b(?<!\d)\d{9}(?!\d)\b", PIIType.SSN, 0.60),

    # Canadian Social Insurance Number (SIN)
    (r"\b\d{3}[\s\-]\d{3}[\s\-]\d{3}\b", PIIType.SSN, 0.85),

    # Email
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", PIIType.EMAIL, 0.98),

    # Phone — international / US formats
    (
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        PIIType.PHONE,
        0.85,
    ),
    # European phone
    (r"\b\+?\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b", PIIType.PHONE, 0.70),

    # Credit card (Visa, MC, Amex, Discover)
    (r"\b(?:\d{4}[-\s]?){3}\d{4}\b", PIIType.CREDIT_CARD, 0.90),
    (r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b", PIIType.CREDIT_CARD, 0.90),

    # IBAN
    (r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){1,7}[\dA-Z]{1,4}\b", PIIType.IBAN, 0.90),

    # Date formats
    (r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b", PIIType.DATE, 0.70),
    (r"\b\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\b", PIIType.DATE, 0.70),
    (
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        PIIType.DATE,
        0.80,
    ),

    # IP address (IPv4)
    (
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        PIIType.IP_ADDRESS,
        0.85,
    ),
    # IPv6 (simplified — common compressed forms)
    (
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        PIIType.IP_ADDRESS,
        0.80,
    ),

    # Passport-like numbers (common formats)
    (r"\b[A-Z]{1,2}\d{6,9}\b", PIIType.PASSPORT, 0.40),

    # Driver's license (US — varies by state, general heuristic)
    (r"\b[A-Z]\d{3}-\d{4}-\d{4}\b", PIIType.DRIVER_LICENSE, 0.70),

    # ── Address patterns ──
    # US street address (e.g. "123 Main Street", "4502 N Broadway Ave")
    (
        r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z][a-z]+\s+){1,3}"
        r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Dr(?:ive)?|Ln|Lane|"
        r"Rd|Road|Ct|Court|Pl(?:ace)?|Way|Cir(?:cle)?|Pkwy|Parkway|"
        r"Ter(?:race)?|Loop|Hwy|Highway)\.?\b",
        PIIType.ADDRESS,
        0.75,
    ),

    # US ZIP code (5-digit or ZIP+4)
    (r"\b\d{5}(?:-\d{4})?\b", PIIType.ADDRESS, 0.35),

    # UK postcode (e.g. "SW1A 1AA", "EC2R 8AH")
    (r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", PIIType.ADDRESS, 0.80),

    # Canadian postal code (e.g. "K1A 0B1")
    (r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", PIIType.ADDRESS, 0.80),

    # ── Vehicle Identification Number (VIN) ──
    (r"\b[A-HJ-NPR-Z0-9]{17}\b", PIIType.CUSTOM, 0.50),

    # ── Healthcare / Government IDs ──
    # UK NHS number (10 digits, often grouped 3-3-4)
    (r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{4}\b", PIIType.CUSTOM, 0.40),
    # US Medicare Beneficiary Identifier (MBI — 11 chars, specific pattern)
    (r"\b[1-9][A-Z](?:[A-Z0-9]){2}-?[A-Z](?:[A-Z0-9]){2}-?[A-Z]{2}\d{2}\b", PIIType.CUSTOM, 0.60),
]

# Compile patterns
_COMPILED_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    (re.compile(pattern, re.IGNORECASE if pii_type != PIIType.IBAN else 0), pii_type, conf)
    for pattern, pii_type, conf in _PATTERNS
]


def detect_regex(text: str) -> list[RegexMatch]:
    """
    Scan text with all regex patterns and return matches.

    Returns non-overlapping matches sorted by position.
    """
    all_matches: list[RegexMatch] = []

    for compiled_re, pii_type, confidence in _COMPILED_PATTERNS:
        for m in compiled_re.finditer(text):
            all_matches.append(RegexMatch(
                start=m.start(),
                end=m.end(),
                text=m.group(),
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
