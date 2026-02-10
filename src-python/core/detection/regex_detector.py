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
    """Validate structure of a French numéro de sécurité sociale."""
    digits = re.sub(r"\s", "", text)
    if len(digits) not in (13, 15):
        return False
    if digits[0] not in "12":
        return False
    month = int(digits[3:5])
    if month < 1 or month > 12:
        return False
    dept = int(digits[5:7])
    if dept < 1 or dept > 99:
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Context keyword proximity boost
# ═══════════════════════════════════════════════════════════════════════════

# Keywords that, when appearing within _CTX_WINDOW chars BEFORE a match,
# significantly increase the likelihood that it's real PII.
_CONTEXT_KEYWORDS: dict[PIIType, list[str]] = {
    PIIType.SSN: [
        "ssn", "social security", "social sec", "tax id", "tin",
        "sécurité sociale", "securite sociale", "sécu", "secu",
        "nir", "n° ss", "n°ss", "numéro ss", "numero ss",
        "steuer-id", "steueridentifikationsnummer", "steuernummer",
        "nif", "dni", "nie", "codice fiscale", "fiscal",
        "rijksregisternummer", "bsn", "burgerservicenummer",
        "national insurance", "ni number", "nino",
    ],
    PIIType.PHONE: [
        "phone", "tel", "téléphone", "telephone", "mobile", "cell",
        "fax", "call", "contact", "number", "numéro", "numero",
        "portable", "fixe", "desk", "direct", "ligne",
        "rufnummer", "telefon", "handy", "mobil",
        "teléfono", "telefono", "cellulare", "celular",
    ],
    PIIType.EMAIL: [
        "email", "e-mail", "mail", "courriel", "courrier",
        "electronic", "électronique", "electronique",
    ],
    PIIType.CREDIT_CARD: [
        "card", "credit", "debit", "visa", "mastercard", "amex",
        "payment", "account", "carte", "bancaire", "cb", "paiement",
        "kreditkarte", "tarjeta", "carta",
    ],
    PIIType.IBAN: [
        "iban", "bank", "account", "swift", "bic",
        "compte", "bancaire", "banque", "rib",
        "kontonummer", "bankverbindung", "konto",
        "cuenta", "conto", "rekening",
    ],
    PIIType.DATE: [
        "born", "birth", "dob", "date of birth", "expires", "expiry",
        "issued", "valid", "deceased", "hired", "terminated",
        "né le", "nee le", "née le", "date de naissance",
        "geburtsdatum", "geboren", "nacimiento",
        "nato il", "nata il", "data di nascita",
    ],
    PIIType.PERSON: [
        "name", "patient", "client", "applicant", "employee",
        "mr", "mrs", "ms", "dr", "prof", "sir", "madam",
        "first name", "last name", "full name", "surname", "given name",
        "maiden name", "alias", "known as",
        # French
        "nom", "prénom", "prenom", "employé", "employe",
        "salarié", "salarie", "monsieur", "madame", "mademoiselle",
        "nom de famille", "nom complet", "identité", "identite",
        # German
        "vorname", "nachname", "familienname", "herr", "frau",
        # Spanish / Italian
        "nombre", "apellido", "cognome", "nome", "señor", "señora",
        "signor", "signora",
    ],
    PIIType.ADDRESS: [
        "address", "street", "city", "state", "zip", "postal",
        "residence", "home", "mailing", "domicile", "located at",
        "lives at", "residing",
        # French
        "adresse", "rue", "avenue", "boulevard", "ville",
        "code postal", "cedex", "lieu-dit", "habite",
        # German
        "anschrift", "straße", "strasse", "plz", "wohnort",
        # Spanish / Italian
        "dirección", "direccion", "calle", "indirizzo", "via",
    ],
    PIIType.LOCATION: [
        "city", "town", "country", "state", "province", "region",
        "county", "municipality", "district", "born in", "located in",
        "based in", "from", "origin", "nationality", "citizen",
        # French
        "ville", "pays", "commune", "département", "departement",
        "région", "region", "né à", "née à", "originaire",
        "nationalité", "nationalite", "domicilié", "domiciliée",
        # German
        "stadt", "land", "gemeinde", "kreis", "bundesland",
        "geboren in", "staatsangehörigkeit",
        # Spanish / Italian
        "ciudad", "país", "pais", "provincia", "comune",
        "nazione", "cittadinanza", "nacionalidad",
    ],
    PIIType.PASSPORT: [
        "passport", "passeport", "reisepass", "pasaporte", "passaporto",
        "travel document", "document de voyage",
    ],
    PIIType.DRIVER_LICENSE: [
        "driver", "license", "licence", "dl", "driving",
        "permis", "conduire", "führerschein", "fuhrerschein",
        "patente", "licencia", "rijbewijs",
    ],
    PIIType.IP_ADDRESS: [
        "ip", "address", "server", "host", "endpoint",
    ],
    PIIType.CUSTOM: [
        "badge", "employee id", "emp id", "staff id", "member id",
        "case", "file", "dossier", "numéro dossier", "n° dossier",
        "reference", "référence", "matricule", "registration",
        "vat", "tva", "tax", "ust-idnr", "ust",
    ],
}

_CTX_WINDOW = 100  # characters to look back for context keywords

def _context_boost(text: str, match_start: int, pii_type: PIIType) -> float:
    """Return a confidence boost (0.0 – 0.25) if context keywords are nearby."""
    keywords = _CONTEXT_KEYWORDS.get(pii_type)
    if not keywords:
        return 0.0

    # Look at the text window before the match
    window_start = max(0, match_start - _CTX_WINDOW)
    context = text[window_start:match_start].lower()

    for kw in keywords:
        if kw in context:
            return 0.25
    return 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Exclusion / negative patterns (common false positives)
# ═══════════════════════════════════════════════════════════════════════════

_EXCLUDE_PATTERNS: list[re.Pattern] = [
    # Page numbers: "Page 3", "page 12 of 20", "p. 5"
    re.compile(r"\bpage\s+\d+", re.IGNORECASE),
    re.compile(r"\bp\.\s*\d+", re.IGNORECASE),
    # Section / figure / table references
    re.compile(r"\b(?:section|sec|figure|fig|table|tab|chapter|ch|item|no|#|art(?:icle)?)\s*\.?\s*\d+", re.IGNORECASE),
    # Version numbers: "v1.2.3", "version 2.0"
    re.compile(r"\bv(?:ersion)?\s*\d+(?:\.\d+)+", re.IGNORECASE),
    # Percentages: "42%", "3.5%"
    re.compile(r"\b\d+(?:\.\d+)?%"),
    # Currency amounts: "$100", "€50.00", "£1,234"
    re.compile(r"[$€£¥]\s*\d"),
    re.compile(r"\b\d[\d,]*\.\d{2}\b"),  # 1,234.56
    # Footnote / endnote markers
    re.compile(r"\[\d{1,3}\]"),
    # File sizes: "10 MB", "3.5 GB"
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)\b", re.IGNORECASE),
    # Time stamps: "10:30", "14:25:30"
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b", re.IGNORECASE),
    # Serial/invoice numbers with specific prefixes
    re.compile(r"\b(?:INV|PO|SO|REF|REQ|TKT|DOC|ID)[-#]?\d+\b", re.IGNORECASE),
]


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


# ═══════════════════════════════════════════════════════════════════════════
# Pattern definitions
# ═══════════════════════════════════════════════════════════════════════════

_NOFLAGS = 0
_IC = re.IGNORECASE

# Each tuple: (pattern, PIIType, base_confidence, re_flags)
_PATTERNS: list[tuple[str, PIIType, float, int]] = [

    # ──────────────────────────────────────────────────────────────────
    # EMAIL  (very high precision — almost never a false positive)
    # ──────────────────────────────────────────────────────────────────
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
     PIIType.EMAIL, 0.98, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # SSN / National ID
    # ──────────────────────────────────────────────────────────────────
    # US SSN — dashed    123-45-6789
    (r"\b\d{3}-\d{2}-\d{4}\b", PIIType.SSN, 0.50, _NOFLAGS),
    # US SSN — spaced    123 45 6789
    (r"\b\d{3}\s\d{2}\s\d{4}\b", PIIType.SSN, 0.40, _NOFLAGS),

    # French NIR — 1 85 05 78 006 084 (42)
    (r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?\d{2,3}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b",
     PIIType.SSN, 0.60, _NOFLAGS),

    # UK National Insurance — AB123456C
    (r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
     PIIType.SSN, 0.65, _NOFLAGS),

    # Spanish DNI — 12345678A
    (r"\b\d{8}[A-Z]\b", PIIType.SSN, 0.45, _NOFLAGS),
    # Spanish NIE — X1234567A
    (r"\b[XYZ]\d{7}[A-Z]\b", PIIType.SSN, 0.55, _NOFLAGS),

    # Italian Codice Fiscale — RSSMRA85M01H501Z (16 alphanum)
    (r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b",
     PIIType.SSN, 0.70, _NOFLAGS),

    # Belgian National Number — YY.MM.DD-XXX.CC
    (r"\b\d{2}\.\d{2}\.\d{2}[-]\d{3}\.\d{2}\b", PIIType.SSN, 0.60, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # PHONE — international coverage
    # ──────────────────────────────────────────────────────────────────
    # US: (555) 123-4567
    (r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}", PIIType.PHONE, 0.92, _NOFLAGS),

    # US/CA bare: 555-123-4567, 555.123.4567
    (r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", PIIType.PHONE, 0.55, _NOFLAGS),

    # International with +  :  +33 6 12 34 56 78, +1-555-987-6543
    (r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}(?:[-.\s]?\d{2,4})?",
     PIIType.PHONE, 0.88, _NOFLAGS),

    # French: 06 12 34 56 78, 06.12.34.56.78, 01-23-45-67-89
    (r"(?:(?:\+|00)33\s?|0)[1-9](?:[\s.\-]?\d{2}){4}",
     PIIType.PHONE, 0.90, _NOFLAGS),

    # UK: 07xxx xxxxxx, 020 xxxx xxxx
    (r"\b0[1-9]\d{2,3}\s?\d{3}\s?\d{3,4}\b", PIIType.PHONE, 0.50, _NOFLAGS),

    # Toll-free US
    (r"\b1[-.]8(?:00|44|55|66|77|88)\b[-.\s]?\d{3}[-.\s]\d{4}\b",
     PIIType.PHONE, 0.90, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # CREDIT CARD
    # ──────────────────────────────────────────────────────────────────
    # 16 digits with separators (Luhn validated post-match)
    (r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b",
     PIIType.CREDIT_CARD, 0.90, _NOFLAGS),
    # 16 consecutive digits starting with 3-6 (Luhn validated)
    (r"\b[3-6]\d{15}\b", PIIType.CREDIT_CARD, 0.40, _NOFLAGS),
    # Amex (15 digits, starts with 34 or 37)
    (r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b",
     PIIType.CREDIT_CARD, 0.90, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # IBAN (with modulo-97 validation post-match)
    # ──────────────────────────────────────────────────────────────────
    # Standard: FR76 1234 5678 9012 3456 7890 123
    (r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?\b",
     PIIType.IBAN, 0.50, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # DATE — context-gated (low base confidence unless near keywords)
    # ──────────────────────────────────────────────────────────────────
    # Numeric: DD/MM/YYYY, MM-DD-YYYY, DD.MM.YYYY
    (r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}\b", PIIType.DATE, 0.35, _NOFLAGS),
    # ISO: YYYY-MM-DD, YYYY/MM/DD
    (r"\b\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\b", PIIType.DATE, 0.35, _NOFLAGS),

    # English month: "January 15, 2024", "Jan 15 2024"
    (
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        PIIType.DATE, 0.40, _IC,
    ),
    # English: "15 January 2024"
    (
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4}\b",
        PIIType.DATE, 0.40, _IC,
    ),

    # French month: "15 janvier 2024", "1er mars 2024"
    (
        r"\b\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|"
        r"juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.45, _IC,
    ),

    # German month: "15. Januar 2024"
    (
        r"\b\d{1,2}\.\s*(?:Januar|Februar|M[aä]rz|April|Mai|Juni|Juli|"
        r"August|September|Oktober|November|Dezember)\s+\d{4}\b",
        PIIType.DATE, 0.45, _IC,
    ),

    # Spanish month
    (
        r"\b\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"(?:\s+(?:de\s+)?\d{4})?\b",
        PIIType.DATE, 0.40, _IC,
    ),

    # ──────────────────────────────────────────────────────────────────
    # IP ADDRESS
    # ──────────────────────────────────────────────────────────────────
    # IPv4
    (
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        PIIType.IP_ADDRESS, 0.85, _NOFLAGS,
    ),
    # IPv6 full
    (
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        PIIType.IP_ADDRESS, 0.80, _NOFLAGS,
    ),

    # ──────────────────────────────────────────────────────────────────
    # PASSPORT
    # ──────────────────────────────────────────────────────────────────
    # Generic EU: 2 uppercase + 7 digits
    (r"\b[A-Z]{2}\d{7}\b", PIIType.PASSPORT, 0.35, _NOFLAGS),
    # German format: C01X00T47
    (r"\b[A-Z]\d{2}[A-Z]\d{2}[A-Z]\d{2}\b", PIIType.PASSPORT, 0.40, _NOFLAGS),
    # French: \d{2}[A-Z]{2}\d{5}
    (r"\b\d{2}[A-Z]{2}\d{5}\b", PIIType.PASSPORT, 0.40, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # DRIVER'S LICENSE
    # ──────────────────────────────────────────────────────────────────
    # US common: A123-4567-8901
    (r"\b[A-Z]\d{3}-\d{4}-\d{4}\b", PIIType.DRIVER_LICENSE, 0.75, _NOFLAGS),
    # US: 1-2 letters + 6-8 digits (many states)
    (r"\b[A-Z]{1,2}\d{6,8}\b", PIIType.DRIVER_LICENSE, 0.30, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # ADDRESS — street patterns (high structural precision)
    # ──────────────────────────────────────────────────────────────────
    # English: "123 Main Street", "45 Oak Ave", "1200 N Broadway Blvd"
    (
        r"\b\d{1,5}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"
        r"\s+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|"
        r"Lane|Ln|Way|Court|Ct|Circle|Cir|Place|Pl|Terrace|Ter|"
        r"Parkway|Pkwy|Highway|Hwy|Trail|Trl)\b\.?",
        PIIType.ADDRESS, 0.80, _IC,
    ),

    # French: "42 rue de la Paix", "12 avenue des Champs-Élysées"
    (
        r"\b\d{1,5}(?:\s*(?:bis|ter))?,?\s+"
        r"(?:rue|avenue|av|boulevard|blvd|impasse|all[ée]e|chemin|place|"
        r"cours|passage|square|quai|route|voie|sentier)"
        r"(?:\s+(?:de\s+(?:la\s+|l['’])?|du\s+|des\s+|d['’]))?[A-ZÀ-Ü]"
        r"[a-zà-ü\-]+(?:\s+[A-ZÀ-Üa-zà-ü\-]+){0,4}\b",
        PIIType.ADDRESS, 0.82, _IC,
    ),

    # German: "Hauptstraße 42", "Berliner Str. 15"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü]+(?:stra[ßs]e|str\.?|weg|gasse|platz|ring|damm|allee|ufer)"
        r"\s+\d{1,5}[a-z]?\b",
        PIIType.ADDRESS, 0.80, _IC,
    ),

    # PO Box / BP / Postfach
    (r"\b(?:P\.?O\.?\s*Box|BP|Bo[iî]te\s*postale|Postfach|Apartado)\s+\d+\b",
     PIIType.ADDRESS, 0.75, _IC),

    # ──────────────────────────────────────────────────────────────────
    # ADDRESS — postal codes (high structural precision)
    # ──────────────────────────────────────────────────────────────────
    # French postal code (5 digits, starts with 0-9, NOT years 1900-2099)
    (r"\b(?<!\d)(?:0[1-9]|[1-9]\d)\d{3}(?!\d)\b"
     r"(?=\s+[A-ZÀ-Ü])",   # must be followed by a town name
     PIIType.ADDRESS, 0.70, _NOFLAGS),
    # French: "75008 Paris", "13100 Aix-en-Provence", "F-75001 Paris"
    (r"\b(?:F-?\s*)?(?:0[1-9]|[1-9]\d)\d{3}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,4}\b",
     PIIType.ADDRESS, 0.82, _NOFLAGS),
    # French with CEDEX
    (r"\b(?:0[1-9]|[1-9]\d)\d{3}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\s+[Cc][Ee][Dd][Ee][Xx](?:\s+\d{1,2})?\b",
     PIIType.ADDRESS, 0.85, _NOFLAGS),
    # German postal code: 5 digits (01000-99999) + city
    (r"\b(?:D-?\s*)?\d{5}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # UK postcode: "SW1A 1AA", "EC2R 8AH", "M1 1AA"
    (r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
     PIIType.ADDRESS, 0.80, _IC),
    # US ZIP: 5 digits or ZIP+4
    (r"\b\d{5}(?:-\d{4})?\b", PIIType.ADDRESS, 0.30, _NOFLAGS),
    # Belgian postal code (4 digits) + city
    (r"\b(?:B-?\s*)?\d{4}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.72, _NOFLAGS),
    # Dutch postal code: "1234 AB"
    (r"\b\d{4}\s?[A-Z]{2}\b", PIIType.ADDRESS, 0.75, _IC),
    # Swiss postal code (4 digits) + city: "CH-8001 Zürich"
    (r"\b(?:CH-?\s*)?\d{4}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.72, _NOFLAGS),
    # Italian CAP (5 digits) + city
    (r"\b(?:I-?\s*)?\d{5}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.72, _NOFLAGS),
    # Spanish postal code (5 digits) + city
    (r"\b(?:E-?\s*)?\d{5}\s+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.72, _NOFLAGS),
    # Canadian: "K1A 0B1"
    (r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", PIIType.ADDRESS, 0.80, _IC),

    # ──────────────────────────────────────────────────────────────────
    # LOCATION — known city & country names (high-recall keyword match)
    # ──────────────────────────────────────────────────────────────────
    # Major world cities (curated list — keeps precision reasonable)
    (r"\b(?:Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|"
     r"Bordeaux|Lille|Rennes|Reims|Toulon|Grenoble|Dijon|Angers|"
     r"Nîmes|Aix-en-Provence|Saint-[ÉE]tienne|Clermont-Ferrand|"
     r"Le\s+Havre|Le\s+Mans|Amiens|Limoges|Tours|Metz|"
     r"Besançon|Perpignan|Orléans|Caen|Mulhouse|Rouen|Nancy|"
     r"London|Manchester|Birmingham|Leeds|Glasgow|Liverpool|Edinburgh|Bristol|"
     r"New\s+York|Los\s+Angeles|Chicago|Houston|Phoenix|San\s+Francisco|"
     r"San\s+Diego|Dallas|Austin|Seattle|Denver|Boston|Miami|Atlanta|"
     r"Washington|Philadelphia|Detroit|Minneapolis|"
     r"Berlin|Munich|München|Hamburg|Frankfurt|Cologne|Köln|Stuttgart|"
     r"Düsseldorf|Leipzig|Dortmund|Essen|Dresden|Bremen|Hannover|"
     r"Madrid|Barcelona|Valencia|Seville|Sevilla|Zaragoza|Málaga|Bilbao|"
     r"Rome|Roma|Milan|Milano|Naples|Napoli|Turin|Torino|Florence|Firenze|"
     r"Venice|Venezia|Bologna|Genoa|Genova|Palermo|"
     r"Amsterdam|Rotterdam|The\s+Hague|Utrecht|"
     r"Brussels|Bruxelles|Antwerp|Anvers|Ghent|Gent|Liège|"
     r"Zürich|Zurich|Geneva|Genève|Basel|Bern|Lausanne|"
     r"Lisbon|Lisboa|Porto|"
     r"Vienna|Wien|Salzburg|Graz|"
     r"Dublin|Cork|"
     r"Toronto|Montreal|Montréal|Vancouver|Ottawa|Calgary|Edmonton|"
     r"Sydney|Melbourne|Brisbane|Perth|Auckland|"
     r"Tokyo|Osaka|Beijing|Shanghai|Singapore|Hong\s+Kong|Seoul|Mumbai|Delhi"
     r")\b",
     PIIType.LOCATION, 0.55, _NOFLAGS),

    # Countries (comprehensive international list)
    (r"\b(?:France|Germany|Deutschland|United\s+Kingdom|United\s+States|"
     r"Italia|Italy|España|Spain|Portugal|Netherlands|Nederland|"
     r"Belgium|Belgique|België|Switzerland|Suisse|Schweiz|Svizzera|"
     r"Austria|Österreich|Ireland|Irlande|"
     r"Luxembourg|Denmark|Danmark|Sweden|Sverige|Norway|Norge|Finland|"
     r"Poland|Polska|Czech\s+Republic|Czechia|Hungary|Romania|"
     r"Greece|Grèce|Croatia|Slovenia|Slovakia|Bulgaria|"
     r"Canada|Mexico|México|Brazil|Brasil|Argentina|Colombia|Chile|"
     r"Australia|New\s+Zealand|Japan|Japon|China|Chine|India|Inde|"
     r"South\s+Korea|Russia|Russie|Turkey|Turquie|"
     r"United\s+Arab\s+Emirates|Saudi\s+Arabia|Israel|Egypt|Égypte|"
     r"South\s+Africa|Nigeria|Morocco|Maroc|Tunisia|Tunisie|Algeria|Algérie|"
     r"Senegal|Sénégal|Ivory\s+Coast|Côte\s+d['']Ivoire|Cameroon|Cameroun"
     r")\b",
     PIIType.LOCATION, 0.50, _IC),

    # ──────────────────────────────────────────────────────────────────
    # PERSON — title-based name patterns (high precision)
    # ──────────────────────────────────────────────────────────────────
    # English: "Mr. John Smith", "Dr. Jane Doe-Peters"
    (
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Sir|Madam|Capt|Sgt|Lt|Col|Gen)"
        r"\.?[ \t]+[A-Z][a-z]{1,20}(?:[ \t]+[A-Z][a-z]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS,
    ),

    # French: "M. Dupont", "Mme Lefèvre", "Mlle Martin"
    (
        r"\b(?:M\.|Mme|Mlle)"
        r"[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS,
    ),

    # German: "Herr Schmidt", "Frau Müller"
    (
        r"\b(?:Herr|Frau)\.?"
        r"[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS,
    ),

    # Spanish: "Sr. García", "Sra. López"
    (
        r"\b(?:Sr|Sra|Srta|Don|Do[ñn]a)"
        r"\.?[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS,
    ),

    # Italian: "Sig. Rossi", "Sig.ra Bianchi"
    (
        r"\b(?:Sig|Sig\.ra|Sig\.na)"
        r"\.?[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS,
    ),

    # ──────────────────────────────────────────────────────────────────
    # ORG — company patterns (structural, high precision)
    # ──────────────────────────────────────────────────────────────────
    # French legal: "CompanyName SA/SAS/SARL/EURL/SCI/SNC/SE"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü\-']{1,25}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü\-']{1,25}){0,4}"
        r"[ \t]+(?:SA|SAS|SARL|EURL|SCI|SNC|SE)\b",
        PIIType.ORG, 0.90, _NOFLAGS,
    ),

    # English legal: "ACME Inc.", "Globex Corp.", "Initech LLC"
    (
        r"\b[A-Z][a-zA-Z&\-']{1,30}"
        r"(?:[ \t]+[A-Z][a-zA-Z&\-']{1,30}){0,4}"
        r"[ \t]+(?:Inc|Corp|LLC|Ltd|LLP|PLC|Co|GmbH|AG|BV|NV)\b\.?",
        PIIType.ORG, 0.88, _IC,
    ),

    # French: "Groupe X", "Société X"
    (
        r"\b(?:Groupe|Soci[ée]t[ée]|Compagnie|[ÉE]tablissements?|Ets|Cabinet|Maison)"
        r"[ \t]+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}){0,3}\b",
        PIIType.ORG, 0.85, _NOFLAGS,
    ),

    # ──────────────────────────────────────────────────────────────────
    # European VAT / Tax ID numbers
    # ──────────────────────────────────────────────────────────────────
    (r"\b(?:FR|DE|ES|IT|BE|NL|AT|PT|PL|SE|DK|FI|IE|LU|CZ|SK|HU|RO|BG|HR|SI|EE|LV|LT|CY|MT|GR|EL|GB)[A-Z0-9]{8,12}\b",
     PIIType.CUSTOM, 0.40, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # LOCATION — GPS coordinates
    # ──────────────────────────────────────────────────────────────────
    (r"\b-?\d{1,3}\.\d{4,8},\s*-?\d{1,3}\.\d{4,8}\b",
     PIIType.LOCATION, 0.75, _NOFLAGS),
]


# ═══════════════════════════════════════════════════════════════════════════
# Label-value patterns (capture-group extraction)
# ═══════════════════════════════════════════════════════════════════════════

# Each pattern MUST have exactly one capture group around the value text.
_LABEL_NAME_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    # ── Person names after labels ──
    # "Name: John Smith", "Full Name: Jane Doe"
    (re.compile(
        r"(?:(?:First|Last|Full|Middle|Sur|Family|Given|Maiden)[ \t]*[Nn]ame|[Nn]ame)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})"
    ), PIIType.PERSON, 0.85),
    # "Patient: John Smith", "Employee: Jane Doe"
    (re.compile(
        r"(?:Patient|Client|Applicant|Employee|Insured|Beneficiary|Claimant|"
        r"Defendant|Plaintiff|Suspect|Witness|Victim|Tenant|Owner|Buyer|Seller)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85),

    # French: "Nom : Dupont", "Prénom : Jean"
    (re.compile(
        r"(?:Nom|Pr[ée]nom|Nom de famille|Nom complet|Identit[ée])"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85),
    # French: "Client : Dupont Jean"
    (re.compile(
        r"(?:Patient|Client|Employ[ée]|Salari[ée]|B[ée]n[ée]ficiaire|"
        r"Assur[ée]|Locataire|Propri[ée]taire|D[ée]fendeur|Demandeur)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85),

    # German: "Vorname: Hans"
    (re.compile(
        r"(?:Vorname|Nachname|Familienname|Name)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85),

    # ── Passport after label ──
    (re.compile(
        r"(?:Passport|Passeport|Reisepass)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([A-Z0-9]{6,9})",
        re.IGNORECASE,
    ), PIIType.PASSPORT, 0.88),

    # ── Driver's license after label ──
    (re.compile(
        r"(?:Driver'?s?\s*Licen[cs]e|DL|Permis\s*(?:de\s*)?conduire|"
        r"F[üu]hrerschein)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([A-Z0-9\-]{6,15})",
        re.IGNORECASE,
    ), PIIType.DRIVER_LICENSE, 0.88),

    # ── SSN after label ──
    (re.compile(
        r"(?:SSN|Social\s*Security|Tax\s*ID|TIN)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*(\d{3}[-\s]?\d{2}[-\s]?\d{4})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92),

    # French SSN after label
    (re.compile(
        r"(?:N°\s*(?:de\s*)?(?:s[ée]curit[ée]\s*sociale|s[ée]cu|SS)|"
        r"Num[ée]ro\s*(?:de\s*)?(?:s[ée]curit[ée]\s*sociale|s[ée]cu|SS)|NIR)"
        r"[ \t]*[:]?[ \t]*([12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?\d{2,3}\s?\d{3}\s?\d{3}(?:\s?\d{2})?)",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92),

    # UK NI after label
    (re.compile(
        r"(?:National\s*Insurance|NI|NINO)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*"
        r"([A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D])",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92),

    # ── IBAN after label ──
    (re.compile(
        r"(?:IBAN|RIB|Compte\s*bancaire|Bankverbindung|Bank\s*[Aa]ccount)"
        r"[ \t]*[:]?[ \t]*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?)",
        re.IGNORECASE,
    ), PIIType.IBAN, 0.90),

    # ── VAT after label ──
    (re.compile(
        r"(?:TVA|VAT|Tax\s*ID|N°\s*TVA|Num[ée]ro\s*(?:de\s*)?TVA|USt-IdNr|NIF|SIREN|SIRET)"
        r"[ \t]*[:]?[ \t]*([A-Z]{0,2}[A-Z0-9]{8,14})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.88),

    # ── Address after label ──
    (re.compile(
        r"(?:Address|Adresse|Anschrift|Direcci[oó]n|Indirizzo|Domicile)"
        r"[ \t]*[:][ \t]*(.{10,80})",
        re.IGNORECASE,
    ), PIIType.ADDRESS, 0.80),

    # ── Date of birth after label ──
    (re.compile(
        r"(?:Date\s*of\s*Birth|DOB|N[ée]\(?e?\)?\s*le|"
        r"Date\s*de\s*naissance|Geburtsdatum|Geboren\s*am|"
        r"Fecha\s*de\s*nacimiento|Data\s*di\s*nascita)"
        r"[ \t]*[:]?[ \t]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        re.IGNORECASE,
    ), PIIType.DATE, 0.92),

    # DOB with verbal month: "Date of Birth: January 15, 1985"
    (re.compile(
        r"(?:Date\s*of\s*Birth|DOB|N[ée]\(?e?\)?\s*le|Date\s*de\s*naissance)"
        r"[ \t]*[:]?[ \t]*(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    ), PIIType.DATE, 0.90),

    # ── Phone after label ──
    (re.compile(
        r"(?:Phone|Tel|T[ée]l[ée]phone|Mobile|Cell|Fax|Portable|Fixe|Rufnummer|Telefon)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([\d\s\+\(\)\.\-]{7,20})",
        re.IGNORECASE,
    ), PIIType.PHONE, 0.88),

    # ── Email after label ──
    (re.compile(
        r"(?:Email|E-mail|Courriel|Mail)"
        r"[ \t]*[:][ \t]*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
        re.IGNORECASE,
    ), PIIType.EMAIL, 0.95),
]


# Compile standalone patterns
_COMPILED_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    (re.compile(pattern, flags), pii_type, conf)
    for pattern, pii_type, conf, flags in _PATTERNS
]


# ═══════════════════════════════════════════════════════════════════════════
# Post-match validators
# ═══════════════════════════════════════════════════════════════════════════

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

    # IBAN: modulo-97 check
    if pii_type == PIIType.IBAN:
        if not _iban_mod97(matched_text):
            return 0.0

    # French SSN: structural validation
    if pii_type == PIIType.SSN:
        ssn_digits = re.sub(r"\s", "", matched_text)
        if len(ssn_digits) in (13, 15) and ssn_digits[0] in "12":
            if not _is_valid_french_ssn(matched_text):
                return 0.0

    return -1.0  # no adjustment


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
            adjusted = _validate_match(text, matched_text, pii_type, m.start())
            if adjusted == 0.0:
                continue
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

    # ── Label-value patterns (capture-group extraction) ──
    for compiled_re, pii_type, base_confidence in _LABEL_NAME_PATTERNS:
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

            boost = _context_boost(text, name_start, pii_type)
            confidence = min(1.0, base_confidence + boost)

            all_matches.append(RegexMatch(
                start=name_start,
                end=name_end,
                text=value_text,
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
