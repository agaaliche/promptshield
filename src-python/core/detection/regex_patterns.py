"""Declarative regex pattern definitions for PII detection.

This module contains all pattern data (standalone patterns, label-value
patterns, context keywords, and exclusion patterns) in a purely
declarative format.  The detection logic lives in ``regex_detector.py``.
"""

from __future__ import annotations

import re
from models.schemas import PIIType

_NOFLAGS = 0
_IC = re.IGNORECASE


# ═══════════════════════════════════════════════════════════════════════════
# Context keyword proximity boost
# ═══════════════════════════════════════════════════════════════════════════

# Keywords that, when appearing within CTX_WINDOW chars BEFORE a match,
# significantly increase the likelihood that it's real PII.
CTX_WINDOW = 100  # characters to look back for context keywords

CONTEXT_KEYWORDS: dict[PIIType, list[str]] = {
    PIIType.SSN: [
        "ssn", "social security", "social sec", "tax id", "tin",
        "sécurité sociale", "securite sociale", "sécu", "secu",
        "nir", "n° ss", "n°ss", "numéro ss", "numero ss",
        "steuer-id", "steueridentifikationsnummer", "steuernummer",
        "nif", "dni", "nie", "codice fiscale", "fiscal",
        "rijksregisternummer", "bsn", "burgerservicenummer",
        "national insurance", "ni number", "nino",
        "nif", "contribuinte", "número de contribuinte",
        # Italian
        "codice fiscale", "tessera sanitaria",
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
        # Financial / administrative / legal
        "dated", "as of", "effective", "signed", "executed",
        "filed", "registered", "incorporated", "established",
        "fiscal year", "period ended", "quarter ended",
        "ending", "closing date", "year end",
        # French financial / legal
        "en date du", "exercice", "période", "periode",
        "clos le", "terminé le", "termine le",
        "signé le", "signe le", "fait le",
        "établi le", "etabli le",
        "pour la période", "bilan au", "arrêté le", "arrete le",
        "comptes au", "clôture", "cloture",
        "daté du", "datée du", "date du",
        # German
        "datum", "stichtag", "zum", "geschäftsjahr",
        "abschlussdatum", "unterzeichnet am",
        # Italian
        "alla data del", "esercizio chiuso",
        "firmato il", "bilancio al",
        # Spanish
        "fecha", "ejercicio cerrado", "firmado el", "balance al",
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
        "piazza", "corso", "viale", "cap", "domicilio", "residenza",
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
        "regione", "città", "nato a", "nata a", "residente",
    ],
    PIIType.PASSPORT: [
        "passport", "passeport", "reisepass", "pasaporte", "passaporto",
        "travel document", "document de voyage",
    ],
    PIIType.DRIVER_LICENSE: [
        "driver", "license", "licence", "dl", "driving",
        "permis", "conduire", "führerschein", "fuhrerschein",
        "patente", "licencia", "rijbewijs",
        "patente di guida", "carta di circolazione",
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


# ═══════════════════════════════════════════════════════════════════════════
# Exclusion / negative patterns (common false positives)
# ═══════════════════════════════════════════════════════════════════════════

EXCLUDE_PATTERNS: list[re.Pattern] = [
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
    # Accounting / financial line items: "Note 5", "Annexe 3"
    re.compile(r"\b(?:note|annexe?|schedule|exhibit)\s+\d+", re.IGNORECASE),
    # Year references in financial context: "FY2024", "exercice 2023"
    re.compile(r"\b(?:FY|fiscal\s+year|exercice|année|annee)\s*\d{4}\b", re.IGNORECASE),
    # Accounting codes / chart of accounts: "4-digit codes" like "1100", "2200"
    re.compile(r"\b(?:compte|account|code)\s+\d{3,6}\b", re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════════
# Standalone pattern definitions
# ═══════════════════════════════════════════════════════════════════════════
# Each tuple: (pattern, PIIType, base_confidence, re_flags)

PATTERNS: list[tuple[str, PIIType, float, int]] = [

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

    # Dutch BSN — 9 digits (11-check validated post-match)
    (r"\b\d{9}\b", PIIType.SSN, 0.25, _NOFLAGS),

    # Portuguese NIF — 9 digits starting with 1-3, 5, 6, 8, 9 (mod-11 validated)
    (r"\b[12356789]\d{8}\b", PIIType.SSN, 0.30, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # PHONE — international coverage
    # ──────────────────────────────────────────────────────────────────
    # US: (555) 123-4567
    (r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}", PIIType.PHONE, 0.92, _NOFLAGS),

    # US/CA bare: 555-123-4567, 555.123.4567
    (r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", PIIType.PHONE, 0.55, _NOFLAGS),

    # International with +  :  +33 6 12 34 56 78, +1-555-987-6543, (+33) 6 12 34 56 78
    (r"\(?\+\d{1,3}\)?[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}(?:[-.\s]?\d{2,4})?",
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
    (r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?\b",
     PIIType.IBAN, 0.85, _NOFLAGS),

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
        PIIType.DATE, 0.60, _IC,
    ),
    # English: "15 January 2024"
    (
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC,
    ),

    # French month: "15 janvier 2024", "1er mars 2024"
    (
        r"\b\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|"
        r"juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC,
    ),

    # German month: "15. Januar 2024"
    (
        r"\b\d{1,2}\.\s*(?:Januar|Februar|M[aä]rz|April|Mai|Juni|Juli|"
        r"August|September|Oktober|November|Dezember)\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC,
    ),

    # Spanish month
    (
        r"\b\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"(?:\s+(?:de\s+)?\d{4})?\b",
        PIIType.DATE, 0.50, _IC,
    ),

    # Italian month: "15 gennaio 2024"
    (
        r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|"
        r"luglio|agosto|settembre|ottobre|novembre|dicembre)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC,
    ),

    # Dutch month: "15 januari 2024"
    (
        r"\b\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|"
        r"juli|augustus|september|oktober|november|december)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC,
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
    (r"\b(?!(?:FR|DE|ES|IT|BE|NL|AT|PT|PL|SE|DK|FI|IE|LU|GB|CH|US|CA)\d)[A-Z]{2}\d{7}\b",
     PIIType.PASSPORT, 0.35, _NOFLAGS),
    # German format: C01X00T47
    (r"\b[A-Z]\d{2}[A-Z]\d{2}[A-Z]\d{2}\b", PIIType.PASSPORT, 0.40, _NOFLAGS),
    # French: \d{2}[A-Z]{2}\d{5}
    (r"\b\d{2}[A-Z]{2}\d{5}\b", PIIType.PASSPORT, 0.40, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # DRIVER'S LICENSE
    # ──────────────────────────────────────────────────────────────────
    # US common: A123-4567-8901
    (r"\b[A-Z]\d{3}-\d{4}-\d{4}\b", PIIType.DRIVER_LICENSE, 0.75, _NOFLAGS),
    # US: 1-2 letters + 7-8 digits
    (r"\b[A-Z]{1,2}\d{7,8}\b", PIIType.DRIVER_LICENSE, 0.30, _NOFLAGS),

    # ──────────────────────────────────────────────────────────────────
    # ADDRESS — street patterns (high structural precision)
    # ──────────────────────────────────────────────────────────────────
    # English: "123 Main Street", "45 Oak Ave", "1200 N Broadway Blvd"
    # NOTE: {0,2} limited to avoid ReDoS on nested quantifiers.
    (
        r"\b\d{1,5}\s+(?:[NSEW]\.?\s+)?[A-Z][a-z]+"
        r"(?:\s+[A-Z][a-z]+){0,2}"
        r"\s+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Road|Rd|"
        r"Lane|Ln|Way|Court|Ct|Circle|Cir|Place|Pl|Terrace|Ter|"
        r"Parkway|Pkwy|Highway|Hwy|Trail|Trl)\b\.?",
        PIIType.ADDRESS, 0.80, _IC,
    ),

    # French: "42 rue de la Paix", "12 avenue des Champs-Élysées"
    # NOTE: Trailing word group limited to {0,3} (was {0,4}) to limit backtracking.
    (
        r"\b\d{1,5}(?:\s*(?:bis|ter))?,?\s+"
        r"(?:rue|avenue|av|boulevard|blvd|impasse|all[ée]e|chemin|place|"
        r"cours|passage|square|quai|route|voie|sentier)"
        r"(?:\s+(?:de\s+(?:la\s+|l[''])?|du\s+|des\s+|d['']))?[A-ZÀ-Ü]"
        r"[a-zà-ü\-]+(?:\s+[A-ZÀ-Üa-zà-ü\-]+){0,3}\b",
        PIIType.ADDRESS, 0.82, _IC,
    ),

    # German: "Hauptstraße 42", "Berliner Str. 15"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü]+(?:stra[ßs]e|str\.?|weg|gasse|platz|ring|damm|allee|ufer)"
        r"\s+\d{1,5}[a-z]?\b",
        PIIType.ADDRESS, 0.80, _IC,
    ),

    # Italian: "Via Roma 42", "Piazza Garibaldi, 1", "Corso Italia 15/A"
    # NOTE: Trailing name group limited to {0,2} (was {0,3}) to limit backtracking.
    (
        r"\b(?:Via|Viale|V\.le|Piazza|P\.zza|Piazzale|Corso|C\.so|"
        r"Largo|Vicolo|Lungomare|Vico|Contrada|Traversa|Salita|Galleria)"
        r"\s+[A-ZÀ-Ü][a-zà-ü\-']+(?:\s+(?:di|del|della|dei|delle|dello|d[ae]l))?\s*"
        r"(?:[A-ZÀ-Ü][a-zà-ü\-']+\s*){0,2}"
        r"(?:[,]?\s*\d{1,5}[/a-zA-Z]?)?\b",
        PIIType.ADDRESS, 0.82, _IC,
    ),

    # PO Box / BP / Postfach / Casella Postale
    (r"\b(?:P\.?O\.?\s*Box|BP|Bo[iî]te\s*postale|Postfach|Apartado|Casella\s+[Pp]ostale|C\.?P\.?)\s+\d+\b",
     PIIType.ADDRESS, 0.75, _IC),

    # ──────────────────────────────────────────────────────────────────
    # ADDRESS — postal codes
    # ──────────────────────────────────────────────────────────────────
    # French postal code (5 digits) must be followed by town name
    (r"\b(?<!\d)(?:0[1-9]|[1-9]\d)\d{3}(?!\d)\b"
     r"(?=[ \t]+[A-ZÀ-Ü])",
     PIIType.ADDRESS, 0.70, _NOFLAGS),
    # French: "75008 Paris", "F-75001 Paris"
    # NOTE: trailing name group limited to {0,3} (was {0,4}).
    (r"\b(?:F-?\s*)?(?:0[1-9]|[1-9]\d)\d{3}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.82, _NOFLAGS),
    # French with CEDEX
    (r"\b(?:0[1-9]|[1-9]\d)\d{3}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,2}\s+[Cc][Ee][Dd][Ee][Xx](?:\s+\d{1,2})?\b",
     PIIType.ADDRESS, 0.85, _NOFLAGS),
    # German postal code: 5 digits + city
    (r"\b(?:D-?\s*)?\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # UK postcode: "SW1A 1AA"
    (r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
     PIIType.ADDRESS, 0.80, _IC),
    # US ZIP+4
    (r"\b\d{5}-\d{4}\b", PIIType.ADDRESS, 0.70, _NOFLAGS),
    # Belgian postal code (4 digits) + city
    (r"\bB-?\s*\d{4}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # Dutch postal code: "1234 AB"
    (r"\b\d{4}\s?[A-Z]{2}\b", PIIType.ADDRESS, 0.75, _IC),
    # Swiss postal code + city
    (r"\bCH-?\s*\d{4}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # Italian CAP + well-known city
    (r"\b(?:I-?\s*)?\d{5}[ \t]+(?:Roma|Milano|Napoli|Torino|Firenze|Venezia|Bologna|Genova|Palermo|Catania|Bari|Verona|Padova|Trieste|Brescia|Parma|Modena|Reggio|Perugia|Livorno|Cagliari|Foggia|Salerno|Ferrara|Rimini|Siracusa|Sassari|Monza|Bergamo|Taranto|Vicenza|Treviso|Novara|Piacenza|Ancona|Andria|Udine|Arezzo|Lecce|Pesaro|Alessandria|Pisa)\b(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,2}",
     PIIType.ADDRESS, 0.80, _NOFLAGS),
    # Italian CAP with I- prefix
    (r"\bI-?\s*\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # Spanish postal code + city
    (r"\bE-?\s*\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS),
    # Canadian: "K1A 0B1"
    (r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b", PIIType.ADDRESS, 0.80, _IC),

    # ──────────────────────────────────────────────────────────────────
    # LOCATION — known city & country names
    # ──────────────────────────────────────────────────────────────────
    # Major world cities
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

    # Countries
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
    # PERSON — title-based name patterns
    # ──────────────────────────────────────────────────────────────────
    # English: "Mr. John Smith"
    (
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Sir|Madam|Capt|Sgt|Lt|Col|Gen)"
        r"\.?[ \t]+[A-Z][a-z]{1,20}(?:[ \t]+[A-Z][a-z]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS,
    ),
    # French: "M. Dupont", "Mme Lefèvre"
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
    # ORG — company patterns
    # ──────────────────────────────────────────────────────────────────
    # French legal: "CompanyName SA/SAS/SARL/EURL/SCI/SNC/SE/SENC"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü\-']{1,25}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü\-']{1,25}){0,4}"
        r"[ \t]+(?:SA|SAS|SARL|EURL|SCI|SNC|SE|SENC|S\.?E\.?N\.?C\.?)\b",
        PIIType.ORG, 0.90, _NOFLAGS,
    ),
    # Multi-language legal suffixes:
    # EN: Inc, Corp, LLC, Ltd, LLP, PLC, Co, LP
    # FR/CA: Ltée, Limitée, Enr., S.E.N.C.
    # DE: GmbH, AG, KG, OHG, e.K., UG, KGaA, mbH
    # ES: S.L., S.A., S.L.U., S.C., S.Coop.
    # IT: S.r.l., S.p.A., S.a.s., S.n.c., S.s.
    # PT: Lda, Ltda, S.A.
    # NL: B.V., N.V., V.O.F., C.V.
    # Nordic: A/S, ApS, AS, ASA, AB, Oy, Oyj, HB, KB
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü&\-']{1,30}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü&\-']{1,30}){0,4}"
        r"[ \t]+(?:"
        r"Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH"
        r"|BV|B\.?V\.?|NV|N\.?V\.?|V\.?O\.?F\.?|C\.?V\.?"
        r"|S\.?A\.?R?\.?L?\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?|S\.?s\.?"
        r"|S\.?Coop\.?"
        r"|Lt[ée]e|Limit[ée]e|Lda|Ltda"
        r"|A/S|ApS|AS|ASA|AB|Oy|Oyj|HB|KB"
        r")\b\.?",
        PIIType.ORG, 0.88, _IC,
    ),
    # Multilingual "Group/Company/Society X" prefix pattern
    # FR: Groupe, Société, Compagnie, Établissements, Cabinet, Maison
    # EN: Group, Company, Corporation, Association, Foundation
    # DE: Firma, Gesellschaft, Verein, Stiftung, Konzern
    # ES: Grupo, Empresa, Compañía, Asociación, Fundación, Corporación
    # IT: Gruppo, Società, Azienda, Impresa, Associazione, Fondazione
    # PT: Grupo, Empresa, Companhia, Associação, Fundação
    # NL: Groep, Bedrijf, Stichting, Vereniging, Maatschappij
    (
        r"\b(?:Groupe|Soci[ée]t[ée]|Compagnie|[ÉE]tablissements?|Ets|Cabinet|Maison"
        r"|Group|Company|Corporation|Association|Foundation|Trust"
        r"|Firma|Gesellschaft|Verein|Stiftung|Konzern"
        r"|Grupo|Empresa|Compa[ñn][ií]a|Asociaci[óo]n|Fundaci[óo]n|Corporaci[óo]n"
        r"|Gruppo|Societ[àa]|Azienda|Impresa|Associazione|Fondazione"
        r"|Companhia|Associa[çc][ãa]o|Funda[çc][ãa]o"
        r"|Groep|Bedrijf|Stichting|Vereniging|Maatschappij)"
        r"[ \t]+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}){0,3}\b",
        PIIType.ORG, 0.85, _NOFLAGS,
    ),
    # Multilingual company with lowercase connecting words:
    # FR: "Les entreprises de restauration B.N. Ltée"
    # ES: "Industrias de Alimentos del Sur S.A."
    # IT: "Società per Azioni del Nord S.p.A."
    # PT: "Companhia de Seguros do Brasil Ltda"
    # DE: "Gesellschaft für Informatik und Technik GmbH"
    # NL: "Bedrijf van de Noord B.V."
    # Allows articles/prepositions between capitalised words,
    # ending with a legal suffix.
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"
        r"(?:[ \t]+(?:"
        # FR: de, du, des, la, le, les, l', d', et, en, aux, au, à
        r"de|du|des|la|le|les|l'|d'|et|en|aux|au|à"
        # ES: de, del, los, las, la, el, y, e, para
        r"|del|los|las|el|y|para"
        # IT: di, del, della, delle, dei, degli, il, lo, per, e
        r"|di|della|delle|dei|degli|il|lo|per"
        # PT: da, do, dos, das, o, a, os, as, para, e
        r"|da|do|dos|das|o|os|as"
        # DE: und, für, der, die, das, den, dem, des, von, zu, zur, zum
        r"|und|f[üu]r|der|die|das|den|dem|von|zu|zur|zum"
        # NL: van, de, het, en, voor, bij, op
        r"|van|het|voor|bij|op"
        r")"
        r"|[ \t]+[A-ZÀ-Ü.][a-zA-Zà-üÀ-Ü.\-']{0,25}){1,8}"
        r"[ \t]+(?:"
        r"Lt[ée]e|Limit[ée]e|Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP"
        r"|SA|SAS|SARL|EURL|SCI|SNC|SE|SENC|S\.?E\.?N\.?C\.?"
        r"|Enr\.?g?\.?"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH"
        r"|BV|B\.?V\.?|NV|N\.?V\.?|V\.?O\.?F\.?|C\.?V\.?"
        r"|S\.?A\.?R?\.?L?\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?|S\.?s\.?"
        r"|S\.?Coop\.?"
        r"|Lda|Ltda"
        r"|A/S|ApS|AS|ASA|AB|Oy|Oyj|HB|KB"
        r")\b\.?",
        PIIType.ORG, 0.90, _IC,
    ),
    # Numbered companies (Quebec/Canada style, also DE HRB numbers)
    (
        r"\b\d{5,10}"
        r"[ \t]+(?:[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,20}[ \t]+){0,3}"
        r"(?:Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH"
        r"|BV|B\.?V\.?|NV|N\.?V\.?"
        r"|S\.?A\.?R?\.?L?\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?"
        r"|Lt[ée]e|Limit[ée]e|Lda|Ltda|Enr\.?g?\.?"
        r"|A/S|ApS|AS|ASA|AB|Oy|Oyj)\b\.?",
        PIIType.ORG, 0.90, _IC,
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
LABEL_NAME_PATTERNS: list[tuple[re.Pattern, PIIType, float]] = [
    # ── Person names after labels ──
    (re.compile(
        r"(?:(?:First|Last|Full|Middle|Sur|Family|Given|Maiden)[ \t]*[Nn]ame|[Nn]ame)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})"
    ), PIIType.PERSON, 0.85),
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
    # Italian: "Nome: Giovanni", "Cognome: Rossi"
    (re.compile(
        r"(?:Nome|Cognome|Nome\s+completo|Nominativo|Intestatario)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85),
    (re.compile(
        r"(?:Paziente|Assistito|Assicurato|Inquilino|Proprietario|Richiedente|"
        r"Imputato|Attore|Convenuto|Testimone|Acquirente|Venditore)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85),

    # ── Passport after label ──
    (re.compile(
        r"(?:Passport|Passeport|Reisepass|Passaporto|Pasaporte)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([A-Z0-9]{6,9})",
        re.IGNORECASE,
    ), PIIType.PASSPORT, 0.88),

    # ── Driver's license after label ──
    (re.compile(
        r"(?:Driver'?s?\s*Licen[cs]e|DL|Permis\s*(?:de\s*)?conduire|"
        r"F[üu]hrerschein|Patente(?:\s*di\s*guida)?|Licencia(?:\s*de\s*conducir)?)"
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
    # Dutch BSN after label
    (re.compile(
        r"(?:BSN|Burgerservicenummer|Sofinummer)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*(\d{9})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92),
    # Portuguese NIF after label
    (re.compile(
        r"(?:NIF|Contribuinte|Número\s*(?:de\s*)?(?:contribuinte|fiscal))"
        r"[ \t]*[:]?[ \t]*([12356789]\d{8})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90),
    # Italian Codice Fiscale after label
    (re.compile(
        r"(?:Codice\s*[Ff]iscale|C\.?F\.?)"
        r"[ \t]*[:]?[ \t]*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92),

    # ── IBAN after label ──
    (re.compile(
        r"(?:IBAN|RIB|Compte\s*bancaire|Bankverbindung|Bank\s*[Aa]ccount|Conto\s*corrente)"
        r"[ \t]*[:]?[ \t]*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?)",
        re.IGNORECASE,
    ), PIIType.IBAN, 0.90),

    # ── VAT after label ──
    (re.compile(
        r"(?:TVA|VAT|Tax\s*ID|N°\s*TVA|Num[ée]ro\s*(?:de\s*)?TVA|USt-IdNr|NIF|SIREN|SIRET|Partita\s*IVA|P\.?IVA)"
        r"[ \t]*[:]?[ \t]*([A-Z]{0,2}[A-Z0-9]{8,14})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.88),

    # ── Address after label ──
    (re.compile(
        r"(?:Address|Adresse|Anschrift|Direcci[oó]n|Indirizzo|Domicile|Domicilio|Residenza)"
        r"[ \t]*[:][ \t]*([^\n\r]{10,80}?)(?=\s*(?:\n|\r|$|(?:Phone|Tel|Email|Fax|Date|Name|Nom|Nome|Cognome)\b))",
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
    # DOB with verbal month
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
