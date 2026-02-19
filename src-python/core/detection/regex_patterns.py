"""Declarative regex pattern definitions for PII detection.

This module contains all pattern data (standalone patterns, label-value
patterns, context keywords, and exclusion patterns) in a purely
declarative format.  The detection logic lives in ``regex_detector.py``.
"""

from __future__ import annotations

import re
from models.schemas import PIIType
from core.detection.detection_config import REGEX_CONTEXT_WINDOW

_NOFLAGS = 0
_IC = re.IGNORECASE


# ═══════════════════════════════════════════════════════════════════════════
# Context keyword proximity boost
# ═══════════════════════════════════════════════════════════════════════════

# Keywords that, when appearing within CTX_WINDOW chars BEFORE a match,
# significantly increase the likelihood that it's real PII.
CTX_WINDOW = REGEX_CONTEXT_WINDOW  # characters to look back for context keywords

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
        # UK NHS
        "nhs", "nhs number", "nhs no",
        # US EIN
        "ein", "employer id", "employer identification", "fein",
        # German health insurance
        "krankenversichertennummer", "versichertennummer", "kvnr",
        "versicherten-nr", "krankenkasse",
        # Patient context
        "patient id", "patient number", "medical record", "mrn",
        "numéro de patient", "patientennummer", "patientenakte",
        # Portuguese
        "niss", "segurança social",
        # Spanish
        "seguridad social", "tarjeta sanitaria", "afiliación",
        # Brazilian
        "cpf", "cadastro",
    ],
    PIIType.PHONE: [
        "phone", "tel", "téléphone", "telephone", "mobile", "cell",
        "fax", "call", "contact", "number", "numéro", "numero",
        "portable", "fixe", "desk", "direct", "ligne",
        "rufnummer", "telefon", "handy", "mobil",
        "teléfono", "telefono", "cellulare", "celular",
        "télécopieur", "telecopieur", "téléc", "telec", "telex",
        "telefax", "facsimile", "facs", "telecópia", "telecopia",
        "téléph", "teleph", "mob", "port", "rufnr", "telecop", "telecóp",
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
        # Sort code / routing
        "sort code", "routing", "aba", "transit",
        "account number", "acct", "numéro de compte",
        "rekeningnummer", "número de cuenta", "numero conto",
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
        # Contract roles
        "signed by", "signature", "witness", "notary", "party",
        "signé par", "notaire", "témoin", "partie",
        "unterschrieben", "notar", "zeuge", "partei",
        "firmado", "testigo", "parte",
        "firmato", "testimone",
        "ondertekend", "getuige",
        # Medical roles
        "physician", "doctor", "attending", "treating",
        "médecin", "praticien", "arzt", "ärztin",
        "medico", "dottore", "arts",
        # Financial roles
        "beneficiary", "payee", "guarantor", "representative",
        "bénéficiaire", "garant", "mandataire",
        "begünstigter", "bürge",
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
        # Company registration
        "siren", "siret", "rcs", "handelsregister", "hrb", "hra",
        "amtsgericht", "registro mercantil", "cif",
        "kvk", "kamer van koophandel", "companies house",
        "partita iva", "p.iva", "cnpj",
        # BIC/SWIFT
        "bic", "swift", "swift code", "bic code",
        # Insurance
        "policy", "police", "polizza", "póliza", "apolice",
        "policennummer", "polisnummer",
        # Medical
        "medical record", "mrn", "patient id", "dossier médical",
        "patientenakte", "cartella clinica", "historial",
        "prontuário", "prontuario",
        "health insurance", "assurance maladie", "krankenkasse",
        "tessera sanitaria", "tarjeta sanitaria", "zorgverzekering",
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
# Each tuple: (pattern, PIIType, base_confidence, re_flags, languages)
# `languages` is a frozenset of ISO-639-1 codes that the pattern applies to,
# or None for universal / language-agnostic patterns.

_ALL = None                          # universal — run for every language
_EN = frozenset({"en"})
_FR = frozenset({"fr"})
_DE = frozenset({"de"})
_ES = frozenset({"es"})
_IT = frozenset({"it"})
_NL = frozenset({"nl"})
_EN_FR = frozenset({"en", "fr"})
_EN_ES = frozenset({"en", "es"})
_EN_FR_DE = frozenset({"en", "fr", "de"})
_ENFR_CA = frozenset({"en", "fr"})   # North American / Canada
_BE = frozenset({"fr", "nl", "de"})  # Belgian languages
_CH = frozenset({"de", "fr", "it"})  # Swiss languages
_PT = frozenset({"pt", "es"})          # Portuguese (+ Spanish fallback)

PATTERNS: list[tuple[str, PIIType, float, int, frozenset[str] | None]] = [

    # ──────────────────────────────────────────────────────────────────
    # EMAIL  (very high precision — almost never a false positive)
    # ──────────────────────────────────────────────────────────────────
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
     PIIType.EMAIL, 0.98, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # SSN / National ID
    # ──────────────────────────────────────────────────────────────────
    # US SSN — dashed    123-45-6789
    (r"\b\d{3}-\d{2}-\d{4}\b", PIIType.SSN, 0.50, _NOFLAGS, _EN),
    # US SSN — spaced    123 45 6789
    (r"\b\d{3}\s\d{2}\s\d{4}\b", PIIType.SSN, 0.40, _NOFLAGS, _EN),

    # French NIR — 1 85 05 78 006 084 (42)
    # Month field: 01-12 (normal), 20 (Corsica), 30-42 (special), 50+ (overseas), 99 (unknown)
    (r"\b[12]\s?\d{2}\s?(?:0[1-9]|[1-9]\d)\s?\d{2,3}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b",
     PIIType.SSN, 0.60, _NOFLAGS, _FR),

    # UK National Insurance — AB123456C
    (r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
     PIIType.SSN, 0.65, _NOFLAGS, _EN),

    # Spanish DNI — 12345678A
    (r"\b\d{8}[A-Z]\b", PIIType.SSN, 0.45, _NOFLAGS, _ES),
    # Spanish NIE — X1234567A
    (r"\b[XYZ]\d{7}[A-Z]\b", PIIType.SSN, 0.55, _NOFLAGS, _ES),

    # Italian Codice Fiscale — RSSMRA85M01H501Z (16 alphanum)
    (r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b",
     PIIType.SSN, 0.70, _NOFLAGS, _IT),

    # Belgian National Number — YY.MM.DD-XXX.CC
    (r"\b\d{2}\.\d{2}\.\d{2}[-]\d{3}\.\d{2}\b", PIIType.SSN, 0.60, _NOFLAGS, _BE),

    # Dutch BSN — 9 digits (11-check validated post-match)
    (r"\b\d{9}\b", PIIType.SSN, 0.25, _NOFLAGS, _NL),

    # Portuguese NIF — 9 digits starting with 1-3, 5, 6, 8, 9 (mod-11 validated)
    (r"\b[12356789]\d{8}\b", PIIType.SSN, 0.30, _NOFLAGS, _PT),

    # ──────────────────────────────────────────────────────────────────
    # PHONE — international coverage
    # ──────────────────────────────────────────────────────────────────
    # US/CA: (555) 123-4567, 1 (555) 123-4567
    (r"(?:\b1[-.\s])?\(\d{3}\)\s?\d{3}[-.\s]?\d{4}", PIIType.PHONE, 0.92, _NOFLAGS, _ENFR_CA),

    # US/CA bare: 555-123-4567, 555.123.4567, 1-555-123-4567, 1.555.123.4567
    (r"\b1[-.\s]\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", PIIType.PHONE, 0.90, _NOFLAGS, _ENFR_CA),
    (r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", PIIType.PHONE, 0.55, _NOFLAGS, _ENFR_CA),

    # International with +  :  +33 6 12 34 56 78, +1-555-987-6543, (+33) 6 12 34 56 78
    (r"\(?\+\d{1,3}\)?[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}(?:[-.\s]?\d{2,4})?",
     PIIType.PHONE, 0.88, _NOFLAGS, _ALL),

    # French: 06 12 34 56 78, 06.12.34.56.78, 01-23-45-67-89
    (r"(?:(?:\+|00)33\s?|0)[1-9](?:[\s.\-]?\d{2}){4}",
     PIIType.PHONE, 0.90, _NOFLAGS, _FR),

    # UK: 07xxx xxxxxx, 020 xxxx xxxx, 020 7946 0958
    (r"\b0[1-9]\d{1,3}\s?\d{3,4}\s?\d{3,4}\b", PIIType.PHONE, 0.50, _NOFLAGS, _EN),

    # German: 030 12345678, 089 1234-5678, 0171 1234567, 0171-1234567
    (r"(?:(?:\+|00)49\s?|0)\d{2,4}[\s/\-]?\d{3,4}[\s\-]?\d{3,5}",
     PIIType.PHONE, 0.85, _NOFLAGS, _DE),

    # Spanish: 91 123 45 67 (landline), 612 345 678 (mobile), 900 123 456
    (r"(?:(?:\+|00)34\s?)?\b(?:9[0-8]\d|[6-7]\d{2})\s?\d{2,3}\s?\d{2}\s?\d{2}\b",
     PIIType.PHONE, 0.80, _NOFLAGS, _ES),

    # Italian: 02 1234 5678, 06 1234 5678, 333 123 4567, 348-1234567
    (r"(?:(?:\+|00)39\s?)?(?:0[1-9]\d{0,2}|3[0-9]{2})[\s\-]?\d{3,4}[\s\-]?\d{3,4}",
     PIIType.PHONE, 0.80, _NOFLAGS, _IT),

    # Dutch: 06-12345678 (mobile), 020-1234567 (landline), 010 123 4567
    (r"(?:(?:\+|00)31\s?|0)\d{1,3}[\s\-]?\d{3,4}[\s\-]?\d{3,4}",
     PIIType.PHONE, 0.80, _NOFLAGS, _NL),

    # Portuguese: 21 123 4567, 91 234 5678, 96 123 4567
    (r"(?:(?:\+|00)351\s?)?\b(?:2\d|9[1-6])\d?\s?\d{3}\s?\d{3,4}\b",
     PIIType.PHONE, 0.80, _NOFLAGS, _PT),

    # Toll-free US/CA
    (r"\b1[-.\s]?8(?:00|44|55|66|77|88)[-.\s]?\d{3}[-.\s]\d{4}\b",
     PIIType.PHONE, 0.90, _NOFLAGS, _ENFR_CA),

    # ──────────────────────────────────────────────────────────────────
    # CREDIT CARD
    # ──────────────────────────────────────────────────────────────────
    # 16 digits with separators (Luhn validated post-match)
    (r"\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}\b",
     PIIType.CREDIT_CARD, 0.90, _NOFLAGS, _ALL),
    # 16 consecutive digits starting with 3-6 (Luhn validated)
    (r"\b[3-6]\d{15}\b", PIIType.CREDIT_CARD, 0.40, _NOFLAGS, _ALL),
    # Amex (15 digits, starts with 34 or 37)
    (r"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b",
     PIIType.CREDIT_CARD, 0.90, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # IBAN (with modulo-97 validation post-match)
    # ──────────────────────────────────────────────────────────────────
    (r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?\b",
     PIIType.IBAN, 0.85, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # DATE — context-gated (low base confidence unless near keywords)
    # ──────────────────────────────────────────────────────────────────
    # Numeric: DD/MM/YYYY, MM-DD-YYYY, DD.MM.YYYY
    (r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}\b", PIIType.DATE, 0.35, _NOFLAGS, _ALL),
    # ISO: YYYY-MM-DD, YYYY/MM/DD
    (r"\b\d{4}[/\-]\d{1,2}[/\-]\d{1,2}\b", PIIType.DATE, 0.35, _NOFLAGS, _ALL),

    # English month: "January 15, 2024", "Jan 15 2024"
    (
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),
    # English: "15 January 2024"
    (
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),

    # French month: "15 janvier 2024", "1er mars 2024"
    (
        r"\b\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|"
        r"juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),

    # German month: "15. Januar 2024"
    (
        r"\b\d{1,2}\.\s*(?:Januar|Februar|M[aä]rz|April|Mai|Juni|Juli|"
        r"August|September|Oktober|November|Dezember)\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),

    # Spanish month
    (
        r"\b\d{1,2}\s+(?:de\s+)?(?:enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"(?:\s+(?:de\s+)?\d{4})?\b",
        PIIType.DATE, 0.50, _IC, _ALL,
    ),

    # Italian month: "15 gennaio 2024"
    (
        r"\b\d{1,2}\s+(?:gennaio|febbraio|marzo|aprile|maggio|giugno|"
        r"luglio|agosto|settembre|ottobre|novembre|dicembre)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),

    # Dutch month: "15 januari 2024"
    (
        r"\b\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|"
        r"juli|augustus|september|oktober|november|december)"
        r"\s+\d{4}\b",
        PIIType.DATE, 0.60, _IC, _ALL,
    ),

    # Portuguese month: "15 de janeiro de 2024", "15 janeiro 2024"
    (
        r"\b\d{1,2}\s+(?:de\s+)?(?:janeiro|fevereiro|mar[çc]o|abril|maio|junho|"
        r"julho|agosto|setembro|outubro|novembro|dezembro)"
        r"(?:\s+(?:de\s+)?\d{4})?\b",
        PIIType.DATE, 0.55, _IC, _ALL,
    ),

    # ──────────────────────────────────────────────────────────────────
    # IP ADDRESS
    # ──────────────────────────────────────────────────────────────────
    # IPv4
    (
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        PIIType.IP_ADDRESS, 0.85, _NOFLAGS, _ALL,
    ),
    # IPv6 full
    (
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        PIIType.IP_ADDRESS, 0.80, _NOFLAGS, _ALL,
    ),

    # ──────────────────────────────────────────────────────────────────
    # PASSPORT
    # ──────────────────────────────────────────────────────────────────
    (r"\b(?!(?:FR|DE|ES|IT|BE|NL|AT|PT|PL|SE|DK|FI|IE|LU|GB|CH|US|CA)\d)[A-Z]{2}\d{7}\b",
     PIIType.PASSPORT, 0.35, _NOFLAGS, _ALL),
    # German format: C01X00T47
    (r"\b[A-Z]\d{2}[A-Z]\d{2}[A-Z]\d{2}\b", PIIType.PASSPORT, 0.40, _NOFLAGS, _DE),
    # French: \d{2}[A-Z]{2}\d{5}
    (r"\b\d{2}[A-Z]{2}\d{5}\b", PIIType.PASSPORT, 0.40, _NOFLAGS, _FR),

    # ──────────────────────────────────────────────────────────────────
    # DRIVER'S LICENSE
    # ──────────────────────────────────────────────────────────────────
    # US common: A123-4567-8901
    (r"\b[A-Z]\d{3}-\d{4}-\d{4}\b", PIIType.DRIVER_LICENSE, 0.75, _NOFLAGS, _EN),
    # US: 1-2 letters + 7-8 digits
    (r"\b[A-Z]{1,2}\d{7,8}\b", PIIType.DRIVER_LICENSE, 0.30, _NOFLAGS, _EN),

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
        PIIType.ADDRESS, 0.80, _IC, _ALL,
    ),

    # French: "42 rue de la Paix", "12 avenue des Champs-Élysées",
    #          "19 rue Adams Bureau 208", "2898, Montée Sandy-Beach"
    # NOTE: Trailing word group limited to {0,3} (was {0,4}) to limit backtracking.
    # The \s+ before [A-ZÀ-Ü] ensures the space after the street type is always
    # consumed, even when there is no prepositional phrase (de/du/des/d').
    (
        r"\b\d{1,5}(?:\s*(?:bis|ter))?,?\s+"
        r"(?:rue|avenue|av\.|boulevard|blvd|impasse|all[ée]e|chemin|place|"
        r"cours|passage|square|quai|route|voie|sentier|"
        r"mont[ée]e|rang|c[ôo]te|ruelle|croissant|promenade)"
        r"(?:\s+(?:de\s+(?:la\s+|l[''])?|du\s+|des\s+|d['']\s*))?\s*[A-ZÀ-Ü]"
        r"[a-zà-ü\-]+(?:[\s,]+[A-ZÀ-Üa-zà-ü0-9\-]+){0,6}\b",
        PIIType.ADDRESS, 0.82, _IC, _ALL,
    ),

    # German: "Hauptstraße 42", "Berliner Str. 15"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü]+(?:stra[ßs]e|str\.?|weg|gasse|platz|ring|damm|allee|ufer)"
        r"\s+\d{1,5}[a-z]?\b",
        PIIType.ADDRESS, 0.80, _IC, _ALL,
    ),

    # Italian: "Via Roma 42", "Piazza Garibaldi, 1", "Corso Italia 15/A"
    # NOTE: Trailing name group limited to {0,2} (was {0,3}) to limit backtracking.
    (
        r"\b(?:Via|Viale|V\.le|Piazza|P\.zza|Piazzale|Corso|C\.so|"
        r"Largo|Vicolo|Lungomare|Vico|Contrada|Traversa|Salita|Galleria)"
        r"\s+[A-ZÀ-Ü][a-zà-ü\-']+(?:\s+(?:di|del|della|dei|delle|dello|d[ae]l))?\s*"
        r"(?:[A-ZÀ-Ü][a-zà-ü\-']+\s*){0,2}"
        r"(?:[,]?\s*\d{1,5}[/a-zA-Z]?)?\b",
        PIIType.ADDRESS, 0.82, _IC, _ALL,
    ),

    # Spanish: "Calle Mayor 5", "Avenida de la Constitución 32", "Paseo del Prado 10"
    (
        r"\b(?:Calle|Avenida|Avda|Paseo|Plaza|Plza|Camino|Carrera|"
        r"Ronda|Travesía|Traves[ií]a|Glorieta|Alameda|Bulevar|Callejón|Callejon)"
        r"(?:\s+(?:de\s+(?:la\s+|las?\s+|los?\s+)?|del\s+))?\s*"
        r"[A-ZÀ-Ü][a-zà-ü\-']+(?:\s+[A-ZÀ-Ü][a-zà-ü\-']+){0,2}"
        r"(?:[,]?\s*(?:n[°º]\.?\s*)?\d{1,5}[/a-zA-Z]?)?\b",
        PIIType.ADDRESS, 0.82, _IC, _ALL,
    ),

    # Dutch: "Keizersgracht 123", "Grote Markt 15", "Nieuwe Binnenweg 10"
    (
        r"\b[A-ZÀ-Ü][a-zà-ü]+"
        r"(?:straat|laan|weg|gracht|plein|dijk|kade|singel|steeg|pad)"
        r"\s+\d{1,5}[a-z]?\b",
        PIIType.ADDRESS, 0.80, _IC, _ALL,
    ),

    # Portuguese: "Rua Augusta 123", "Avenida da Liberdade 45", "Praça do Comércio 10"
    (
        r"\b(?:Rua|Avenida|Av\.|Praça|Praca|Travessa|Largo|Alameda|Estrada|"
        r"Calçada|Calcada|Beco)"
        r"(?:\s+(?:da\s+|do\s+|dos\s+|das\s+|de\s+))?\s*"
        r"[A-ZÀ-Ü][a-zà-ü\-']+(?:\s+[A-ZÀ-Ü][a-zà-ü\-']+){0,2}"
        r"(?:[,]?\s*(?:n[°º]\.?\s*)?\d{1,5}[/a-zA-Z]?)?\b",
        PIIType.ADDRESS, 0.82, _IC, _ALL,
    ),

    # PO Box / BP / Postfach / Casella Postale
    (r"\b(?:P\.?O\.?\s*Box|BP|Bo[iî]te\s*postale|Postfach|Apartado|Casella\s+[Pp]ostale|C\.?P\.?)\s+\d+\b",
     PIIType.ADDRESS, 0.75, _IC, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # ADDRESS — postal codes
    # ──────────────────────────────────────────────────────────────────
    # French postal code (5 digits) must be followed by town name
    (r"\b(?<!\d)(?:0[1-9]|[1-9]\d)\d{3}(?!\d)\b"
     r"(?=[ \t]+[A-ZÀ-Ü])",
     PIIType.ADDRESS, 0.70, _NOFLAGS, _ALL),
    # French: "75008 Paris", "F-75001 Paris"
    # NOTE: trailing name group limited to {0,3} (was {0,4}).
    (r"\b(?:F-?\s*)?(?:0[1-9]|[1-9]\d)\d{3}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.82, _NOFLAGS, _ALL),
    # French with CEDEX
    (r"\b(?:0[1-9]|[1-9]\d)\d{3}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,2}\s+[Cc][Ee][Dd][Ee][Xx](?:\s+\d{1,2})?\b",
     PIIType.ADDRESS, 0.85, _NOFLAGS, _ALL),
    # German postal code: 5 digits + city
    (r"\b(?:D-?\s*)?\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS, _ALL),
    # UK postcode: "SW1A 1AA"
    (r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
     PIIType.ADDRESS, 0.80, _IC, _ALL),
    # US ZIP+4
    (r"\b\d{5}-\d{4}\b", PIIType.ADDRESS, 0.70, _NOFLAGS, _ALL),
    # Belgian postal code (4 digits) + city
    (r"\bB-?\s*\d{4}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS, _ALL),
    # Dutch postal code: "1234 AB" — must be uppercase (case-sensitive)
    # Restricted to NL-only to avoid FPs like "2026 ET" in French docs.
    (r"\b\d{4}\s?[A-Z]{2}\b", PIIType.ADDRESS, 0.75, _NOFLAGS, _NL),
    # Swiss postal code + city
    (r"\bCH-?\s*\d{4}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS, _ALL),
    # Italian CAP + well-known city
    (r"\b(?:I-?\s*)?\d{5}[ \t]+(?:Roma|Milano|Napoli|Torino|Firenze|Venezia|Bologna|Genova|Palermo|Catania|Bari|Verona|Padova|Trieste|Brescia|Parma|Modena|Reggio|Perugia|Livorno|Cagliari|Foggia|Salerno|Ferrara|Rimini|Siracusa|Sassari|Monza|Bergamo|Taranto|Vicenza|Treviso|Novara|Piacenza|Ancona|Andria|Udine|Arezzo|Lecce|Pesaro|Alessandria|Pisa)\b(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,2}",
     PIIType.ADDRESS, 0.80, _NOFLAGS, _ALL),
    # Italian CAP with I- prefix
    (r"\bI-?\s*\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS, _ALL),
    # Spanish postal code + city
    (r"\bE-?\s*\d{5}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.75, _NOFLAGS, _ALL),
    # Portuguese postal code: 1000-001 Lisboa
    (r"\b\d{4}-\d{3}[ \t]+[A-ZÀ-Ü][a-zà-ü]+(?:[\s\-][A-ZÀ-Üa-zà-ü]+){0,3}\b",
     PIIType.ADDRESS, 0.80, _NOFLAGS, _ALL),
    # Canadian: "K1A 0B1", "G4X-1W7"
    (r"\b[A-Z]\d[A-Z][\s\-]?\d[A-Z]\d\b", PIIType.ADDRESS, 0.80, _IC, _ALL),

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
     PIIType.LOCATION, 0.55, _NOFLAGS, _ALL),

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
     PIIType.LOCATION, 0.50, _IC, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # PERSON — title-based name patterns
    # ──────────────────────────────────────────────────────────────────
    # English: "Mr. John Smith"
    (
        r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Rev|Sir|Madam|Capt|Sgt|Lt|Col|Gen)"
        r"\.?[ \t]+[A-Z][a-z]{1,20}(?:[ \t]+[A-Z][a-z]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS, _EN,
    ),
    # French: "M. Dupont", "Mme Lefèvre"
    (
        r"\b(?:M\.|Mme|Mlle)"
        r"[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS, _FR,
    ),
    # German: "Herr Schmidt", "Frau Müller"
    (
        r"\b(?:Herr|Frau)\.?"
        r"[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.88, _NOFLAGS, _DE,
    ),
    # Spanish: "Sr. García", "Sra. López"
    (
        r"\b(?:Sr|Sra|Srta|Don|Do[ñn]a)"
        r"\.?[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS, _ES,
    ),
    # Italian: "Sig. Rossi", "Sig.ra Bianchi"
    (
        r"\b(?:Sig|Sig\.ra|Sig\.na)"
        r"\.?[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS, _IT,
    ),
    # Dutch: "Dhr. de Vries", "Mw. Jansen", "Mevr. van den Berg"
    (
        r"\b(?:Dhr|Mw|Mevr|Ir|Ing|Drs|Mr|Ds)"
        r"\.?[ \t]+(?:(?:de|van|den|der|het|ten|ter|te)\s+)*"
        r"[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS, _NL,
    ),
    # Portuguese: "Sr. Silva", "Sra. Santos", "Dr. Ferreira"
    (
        r"\b(?:Sr|Sra|Srta|Dr|Dra|Prof|Eng)"
        r"\.?[ \t]+(?:(?:de|da|do|dos|das)\s+)*"
        r"[A-ZÀ-Ü][a-zà-ü]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zà-ü]{1,20}){0,3}\b",
        PIIType.PERSON, 0.85, _NOFLAGS, _PT,
    ),

    # ──────────────────────────────────────────────────────────────────
    # ORG — company patterns
    # ──────────────────────────────────────────────────────────────────
    # French legal: "CompanyName SA/SAS/SARL/EURL/SCI/SNC/SE/SENC"
    # _NOFLAGS so first char of each word must be uppercase.
    # SA/SE are case-sensitive to avoid matching French "sa"/"se".
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}){0,4}"
        r"\s+(?:(?i:SAS|SARL|EURL|SCI|SNC|SENC|S\.?E\.?N\.?C\.?)|SA|SE)\b\.?",
        PIIType.ORG, 0.90, _NOFLAGS, _ALL,
    ),
    # Numbered companies: "9169270 Canada inc.", "123456 Québec Ltd."
    # Common in Canada/Quebec where numbered corps are legal entities.
    (
        r"\b\d{4,10}\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}){0,3}"
        r"\s+(?i:Inc|Corp|LLC|Ltd|LLP|Ltée|Limitée|Enr|S\.?E\.?N\.?C\.?)\b\.?",
        PIIType.ORG, 0.92, _NOFLAGS, _ALL,
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
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü&\-']{1,30}){0,4}"
        r"\s+(?:(?i:"
        r"Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP|SAS"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH|e\.?V\.?"
        r"|BV|B\.?V\.?|NV|N\.?V\.?|V\.?O\.?F\.?|C\.?V\.?"
        r"|S\.?A\.?R\.?L\.?|S\.A\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?|S\.?s\.?"
        r"|S\.?Coop\.?"
        r"|Lt[ée]e|Limit[ée]e|Lda|Ltda"
        r"|A/S|ApS|ASA|AB|Oy|Oyj|HB|KB"
        r")|SA|SE|AS)\b\.?",
        PIIType.ORG, 0.88, _NOFLAGS, _ALL,
    ),
    # German compound legal forms: "Name GmbH & Co. KG", "Name SE & Co. KGaA"
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü&\-']{1,30}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü&\-']{1,30}){0,4}"
        r"\s+(?:(?i:"
        r"GmbH\s*&\s*Co\.?\s*(?:KG|OHG|KGaA)"
        r"|SE\s*&\s*Co\.?\s*KGaA"
        r"|UG\s*\(haftungsbeschr[äa]nkt\)"
        r"))\b\.?",
        PIIType.ORG, 0.92, _NOFLAGS, _ALL,
    ),
    # German association/club: "1. FC Union Berlin e.V."
    # Allows numbers and dots at the start for clubs like "1. FC"
    (
        r"\b(?:\d{1,2}\.\s*)?[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-]{1,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-]{1,25}){0,4}"
        r"\s+(?i:e\.?\s?V\.?)\b\.?",
        PIIType.ORG, 0.90, _NOFLAGS, _ALL,
    ),
    # Quoted company names followed by legal suffix (DE style):
    # '"An der Alten Försterei" Stadionbetriebs AG'
    (
        r'["\u201C\u201E\u00AB][^"\u201D\u201F\u00BB]{3,60}["\u201D\u201F\u00BB]'
        r'\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-]{1,25}'
        r'(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-]{1,25}){0,2}'
        r'\s+(?:(?i:'
        r'GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH|e\.?V\.?'
        r'|GmbH\s*&\s*Co\.?\s*(?:KG|OHG|KGaA)'
        r'|Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP|SAS'
        r'|S\.?A\.?R\.?L\.?|S\.A\.?|S\.?R\.?L\.?'
        r')|SA|SE|AS)\b\.?',
        PIIType.ORG, 0.92, _NOFLAGS, _ALL,
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
        r"\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,25}){0,3}\b",
        PIIType.ORG, 0.85, _NOFLAGS, _ALL,
    ),
    # Multilingual company with lowercase connecting words:
    # FR: "Les entreprises de restauration B.N. Ltée"
    # ES: "Industrias de Alimentos del Sur S.A."
    # IT: "Società per Azioni del Nord S.p.A."
    # PT: "Companhia de Seguros do Brasil Ltda"
    # DE: "Gesellschaft für Informatik und Technik GmbH"
    # NL: "Bedrijf van de Noord B.V."
    # Allows articles/prepositions between capitalised words,
    # ending with a legal suffix. After connecting words, next word
    # can start with lowercase (e.g., "de restauration").
    # Also allows plain lowercase words (body text: "Les entreprises … ltée").
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # First word: must start with capital
        r"(?:"  # Then repeat 1-5 times:
        r"\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # Capitalized word
        r"|\s+(?i:"  # OR connecting word followed by any word (case-insensitive)
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
        r"\s+[a-zA-ZÀ-üÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # After connecting word, allow lowercase start
        r"|\s+[a-zà-ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # OR plain lowercase word (body text)
        r"){1,5}"
        r"\s+(?:(?i:"  # Make suffix case-insensitive (SA/SE/AS are case-sensitive outside)
        r"Lt[ée]e|Limit[ée]e|Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP|SAS"
        r"|SARL|EURL|SCI|SNC|SENC|S\.?E\.?N\.?C\.?"
        r"|Enr\.?g?\.?"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH|e\.?V\.?"
        r"|GmbH\s*&\s*Co\.?\s*(?:KG|OHG|KGaA)"
        r"|BV|B\.?V\.?|NV|N\.?V\.?|V\.?O\.?F\.?|C\.?V\.?"
        r"|S\.?A\.?R\.?L\.?|S\.A\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?|S\.?s\.?"
        r"|S\.?Coop\.?"
        r"|Lda|Ltda"
        r"|A/S|ApS|ASA|AB|Oy|Oyj|HB|KB"
        r")|SA|SE|AS)\b\.?",
        PIIType.ORG, 0.90, _NOFLAGS, _ALL,
    ),
    # Numbered companies (Quebec/Canada style with dashes, also DE HRB numbers)
    # Matches: "9425-7524 Québec inc." or "123456 Company Inc."
    # Requires at least one word (3+ chars) between number and suffix to avoid postal codes
    (
        r"\b\d{3,10}(?:-\d{3,10})?"  # 3-10 digits, optionally followed by dash and more digits
        r"\s+(?:[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,20}\s+){1,3}"  # Require 1-3 words (min 3 chars each)
        r"(?:(?i:Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP|SAS"
        r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH|e\.?V\.?"
        r"|GmbH\s*&\s*Co\.?\s*(?:KG|OHG|KGaA)"
        r"|BV|B\.?V\.?|NV|N\.?V\.?"
        r"|S\.?A\.?R\.?L\.?|S\.A\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
        r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?"
        r"|Lt[ée]e|Limit[ée]e|Lda|Ltda|Enr\.?g?\.?"
        r"|A/S|ApS|ASA|AB|Oy|Oyj"
        r")|SA|SE|AS)\b\.?",
        PIIType.ORG, 0.90, _NOFLAGS, _ALL,
    ),
    # Company name appearing before French financial document headers (without legal suffix).
    # Pattern: Capitalized multi-word phrase (2-4 words) immediately followed by
    # common French financial statement titles. Uses lookahead to capture only
    # the company name, not the header.
    # E.g. "Filets Sports Gaspésiens\nÉTAT DES RÉSULTATS" → captures "Filets Sports Gaspésiens"
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"  # First word
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"  # 1-3 more capitalized words
        r"(?=\s*\n\s*(?:"  # Lookahead: newline followed by French financial header
        r"[ÉE]TAT\s+(?:DES\s+R[ÉE]SULTATS|DU\s+CAPITAL|FINANCIER)"
        r"|BILAN|COMPTE\s+DE\s+R[ÉE]SULTAT"
        r"|BUDGET|RAPPORT\s+(?:ANNUEL|FINANCIER)"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _FR,
    ),
    # English: company name before financial headers
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"
        r"(?=\s*\n\s*(?:"
        r"INCOME\s+STATEMENT|BALANCE\s+SHEET|STATEMENT\s+OF\s+(?:FINANCIAL\s+POSITION|CASH\s+FLOWS|OPERATIONS)"
        r"|PROFIT\s+AND\s+LOSS|ANNUAL\s+REPORT|FINANCIAL\s+STATEMENTS?"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _EN,
    ),
    # German: company name before financial headers
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"
        r"(?=\s*\n\s*(?:"
        r"BILANZ|GEWINN-?\s*UND\s*VERLUSTRECHNUNG|JAHRESABSCHLUSS"
        r"|LAGEBERICHT|KAPITALFLUSSRECHNUNG|GESCH[ÄA]FTSBERICHT"
        r"|ERFOLGSRECHNUNG|ANHANG\s+ZUM\s+JAHRESABSCHLUSS"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _DE,
    ),
    # Spanish: company name before financial headers
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"
        r"(?=\s*\n\s*(?:"
        r"BALANCE\s+(?:GENERAL|DE\s+SITUACI[ÓO]N)|ESTADO\s+DE\s+RESULTADOS"
        r"|CUENTA\s+DE\s+(?:P[ÉE]RDIDAS\s+Y\s+GANANCIAS|RESULTADOS)"
        r"|INFORME\s+(?:ANUAL|FINANCIERO)|MEMORIA\s+ANUAL"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _ES,
    ),
    # Italian: company name before financial headers
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"
        r"(?=\s*\n\s*(?:"
        r"BILANCIO|CONTO\s+ECONOMICO|STATO\s+PATRIMONIALE"
        r"|RENDICONTO\s+FINANZIARIO|RELAZIONE\s+(?:SULLA\s+GESTIONE|ANNUALE)"
        r"|NOTA\s+INTEGRATIVA"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _IT,
    ),
    # Dutch: company name before financial headers
    (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{2,25}){1,3}"
        r"(?=\s*\n\s*(?:"
        r"BALANS|WINST-?\s*EN\s*VERLIESREKENING|JAARREKENING"
        r"|RESULTATENREKENING|KASSTROOMOVERZICHT"
        r"|JAARVERSLAG|TOELICHTING"
        r"))",
        PIIType.ORG, 0.88, re.IGNORECASE, _NL,
    ),

    # ──────────────────────────────────────────────────────────────────
    # European VAT / Tax ID numbers
    # ──────────────────────────────────────────────────────────────────
    (r"\b(?:FR|DE|ES|IT|BE|NL|AT|PT|PL|SE|DK|FI|IE|LU|CZ|SK|HU|RO|BG|HR|SI|EE|LV|LT|CY|MT|GR|EL|GB)[A-Z0-9]{8,12}\b",
     PIIType.CUSTOM, 0.40, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # BIC / SWIFT codes  (financial / contracts)
    # ──────────────────────────────────────────────────────────────────
    # 8 or 11 chars:  BNPAFRPP, DEUTDEFF500
    (r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b",
     PIIType.CUSTOM, 0.35, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # French SIREN / SIRET  (contracts / financial)
    # ──────────────────────────────────────────────────────────────────
    # SIREN — 9 digits grouped 3×3:  362 521 879
    (r"\b\d{3}\s\d{3}\s\d{3}\b",
     PIIType.CUSTOM, 0.40, _NOFLAGS, _FR),
    # SIRET — 14 digits grouped 3×3×3+5:  362 521 879 00034
    (r"\b\d{3}\s\d{3}\s\d{3}\s\d{5}\b",
     PIIType.CUSTOM, 0.55, _NOFLAGS, _FR),
    # SIRET compact or dotted: 36252187900034, 362.521.879.00034
    (r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[.\s]?\d{5}\b",
     PIIType.CUSTOM, 0.50, _NOFLAGS, _FR),

    # ──────────────────────────────────────────────────────────────────
    # German Handelsregister (HRB/HRA)  (contracts)
    # ──────────────────────────────────────────────────────────────────
    # HRB 12345, HRA 6789, HRB 137077 B
    (r"\bHR[AB]\s?\d{3,7}(?:\s?[A-Z])?\b",
     PIIType.CUSTOM, 0.70, _NOFLAGS, _DE),

    # ──────────────────────────────────────────────────────────────────
    # US EIN — Employer Identification Number  (contracts / financial)
    # ──────────────────────────────────────────────────────────────────
    # XX-XXXXXXX (2 digits, dash, 7 digits)
    (r"\b\d{2}-\d{7}\b",
     PIIType.SSN, 0.35, _NOFLAGS, _EN),

    # ──────────────────────────────────────────────────────────────────
    # Spanish CIF — company tax ID  (contracts / financial)
    # ──────────────────────────────────────────────────────────────────
    # Letter (A-H,J,N,P-S,U,V,W) + 7 digits + control (digit or letter)
    (r"\b[ABCDEFGHJNPQRSUVW]\d{7}[A-J0-9]\b",
     PIIType.CUSTOM, 0.45, _NOFLAGS, _ES),

    # ──────────────────────────────────────────────────────────────────
    # Italian Partita IVA — 11 digits  (financial / contracts)
    # ──────────────────────────────────────────────────────────────────
    (r"\b\d{11}\b",
     PIIType.CUSTOM, 0.25, _NOFLAGS, _IT),

    # ──────────────────────────────────────────────────────────────────
    # UK NHS Number — 10 digits  (patient / medical)
    # ──────────────────────────────────────────────────────────────────
    # Commonly displayed as 3-3-4: 943 476 5919
    (r"\b\d{3}\s\d{3}\s\d{4}\b",
     PIIType.SSN, 0.30, _NOFLAGS, _EN),
    # Compact 10 digits (very low confidence — boosted by context)
    (r"\b\d{10}\b",
     PIIType.SSN, 0.20, _NOFLAGS, _EN),

    # ──────────────────────────────────────────────────────────────────
    # German Krankenversichertennummer  (patient / medical)
    # ──────────────────────────────────────────────────────────────────
    # Letter + 9 digits:  A123456789
    (r"\b[A-Z]\d{9}\b",
     PIIType.SSN, 0.35, _NOFLAGS, _DE),

    # ──────────────────────────────────────────────────────────────────
    # German Personalausweisnummer (ID card)  (contracts)
    # ──────────────────────────────────────────────────────────────────
    # New format: LXXXXXXXX (letter + 8 alphanum), e.g. T22000129
    (r"\b[CFGHJKLMNPRTVWXYZ]\d{2}[0-9CFGHJKLMNPRTVWXYZ]{6}\b",
     PIIType.SSN, 0.35, _NOFLAGS, _DE),

    # ──────────────────────────────────────────────────────────────────
    # Italian Carta d'Identità  (contracts / patient)
    # ──────────────────────────────────────────────────────────────────
    # Old format: AA 1234567, New format: CA12345AA
    (r"\b[A-Z]{2}\s?\d{5}[A-Z]{2}\b",
     PIIType.SSN, 0.40, _NOFLAGS, _IT),

    # ──────────────────────────────────────────────────────────────────
    # UK Sort Code + Account  (financial / contracts)
    # ──────────────────────────────────────────────────────────────────
    # 12-34-56 12345678
    (r"\b\d{2}-\d{2}-\d{2}\s+\d{8}\b",
     PIIType.IBAN, 0.70, _NOFLAGS, _EN),

    # ──────────────────────────────────────────────────────────────────
    # US Routing + Account Number  (financial / contracts)
    # ──────────────────────────────────────────────────────────────────
    # 9-digit routing number followed by account digits
    (r"\b\d{9}\s+\d{6,17}\b",
     PIIType.IBAN, 0.30, _NOFLAGS, _EN),

    # ──────────────────────────────────────────────────────────────────
    # Portuguese NISS — Social Security  (patient / contracts)
    # ──────────────────────────────────────────────────────────────────
    # 11 digits
    (r"\b\d{11}\b",
     PIIType.SSN, 0.20, _NOFLAGS, _PT),

    # ──────────────────────────────────────────────────────────────────
    # Spanish Tarjeta Sanitaria  (patient)
    # ──────────────────────────────────────────────────────────────────
    # Format varies by region but many follow: 2-letter province + 12 digits
    # or NASS format: XX / XXXXXXXXXX / XX
    (r"\b[A-Z]{2}\d{12}\b",
     PIIType.SSN, 0.30, _NOFLAGS, _ES),

    # ──────────────────────────────────────────────────────────────────
    # Medical Record Number patterns  (patient)
    # ──────────────────────────────────────────────────────────────────
    # Common format: MRN-XXXXXXX, MR-XXXX, Dossier-XXXX
    (r"\b(?:MRN|MR|PAT|DOS)\s*[-:]\s*[A-Z0-9]{4,12}\b",
     PIIType.CUSTOM, 0.70, _IC, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # Insurance Policy Number patterns  (patient / financial)
    # ──────────────────────────────────────────────────────────────────
    # Letters + digits, 10-16 chars — common group health policy IDs
    # Require 3+ letter prefix to reduce FPs (COVID19, ISBN10, etc.)
    (r"\b[A-Z]{3,4}\d{7,12}\b",
     PIIType.CUSTOM, 0.22, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # LOCATION — GPS coordinates
    # ──────────────────────────────────────────────────────────────────
    (r"\b-?\d{1,3}\.\d{4,8},\s*-?\d{1,3}\.\d{4,8}\b",
     PIIType.LOCATION, 0.75, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # M1: European national ID numbers (Scandinavian, Polish, Czech, etc.)
    # ──────────────────────────────────────────────────────────────────
    # Swedish personnummer: YYMMDD-XXXX or YYYYMMDDXXXX
    (r"\b\d{6}[-+]?\d{4}\b",
     PIIType.SSN, 0.25, _NOFLAGS, _ALL),
    # Danish CPR: DDMMYY-XXXX
    (r"\b\d{6}-\d{4}\b",
     PIIType.SSN, 0.30, _NOFLAGS, _ALL),
    # Finnish HETU: DDMMYY[A+-]\d{3}[0-9A-Y]
    (r"\b\d{6}[A+\-]\d{3}[0-9A-Y]\b",
     PIIType.SSN, 0.35, _NOFLAGS, _ALL),
    # Polish PESEL: 11 digits (birth-date encoded)
    # Already covered by \b\d{11}\b patterns — skip duplicate
    # Czech/Slovak rodné číslo: YYMMDD/XXXX (with slash)
    (r"\b\d{6}/\d{3,4}\b",
     PIIType.SSN, 0.35, _NOFLAGS, _ALL),
    # Hungarian személyi szám: 8 digits
    (r"\b\d{8}\b",
     PIIType.SSN, 0.15, _NOFLAGS, _ALL),
    # Romanian CNP: 13 digits starting with 1-8
    (r"\b[1-8]\d{12}\b",
     PIIType.SSN, 0.30, _NOFLAGS, _ALL),

    # ──────────────────────────────────────────────────────────────────
    # M2: Passport numbers (US, UK, IT, ES)
    # ──────────────────────────────────────────────────────────────────
    # US passport: 9 digits
    # Already covered by 9-digit SSN + BSN/NIF validation
    # UK passport: 9 digits — same as above
    # Italian passport: 2 letters + 7 digits (AA1234567)
    (r"\b[A-Z]{2}\d{7}\b",
     PIIType.PASSPORT, 0.25, _NOFLAGS, _IT),
    # Spanish passport: 3 letters + 6 digits (AAA123456)
    (r"\b[A-Z]{3}\d{6}\b",
     PIIType.PASSPORT, 0.25, _NOFLAGS, _ES),
    # French passport: 2 digits + 2 letters + 5 digits (12AB34567)
    (r"\b\d{2}[A-Z]{2}\d{5}\b",
     PIIType.PASSPORT, 0.25, _NOFLAGS, _FR),
    # German passport: C/F/G/H/J/K + 8 alphanumeric
    (r"\b[CFGHJK][0-9CFGHJKLMNPRTVWXYZ]{8}\b",
     PIIType.PASSPORT, 0.25, _NOFLAGS, _DE),

    # ──────────────────────────────────────────────────────────────────
    # M3: Dates with 2-digit year (DD/MM/YY, MM/DD/YY, YY-MM-DD)
    # ──────────────────────────────────────────────────────────────────
    # These are already partially covered by the main date pattern;
    # add explicit 2-digit-year pattern with lower confidence.
    (r"\b(?:0[1-9]|[12]\d|3[01])[/\-.](?:0[1-9]|1[0-2])[/\-.]\d{2}\b",
     PIIType.DATE, 0.35, _NOFLAGS, _ALL),
]


# ═══════════════════════════════════════════════════════════════════════════
# Label-value patterns (capture-group extraction)
# ═══════════════════════════════════════════════════════════════════════════

# Each pattern MUST have exactly one capture group around the value text.
LABEL_NAME_PATTERNS: list[tuple[re.Pattern, PIIType, float, frozenset[str] | None]] = [
    # ── Person names after labels ──
    (re.compile(
        r"(?:(?:First|Last|Full|Middle|Sur|Family|Given|Maiden)[ \t]*[Nn]ame|[Nn]ame)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})"
    ), PIIType.PERSON, 0.85, _EN),
    (re.compile(
        r"(?:Patient|Client|Applicant|Employee|Insured|Beneficiary|Claimant|"
        r"Defendant|Plaintiff|Suspect|Witness|Victim|Tenant|Owner|Buyer|Seller)"
        r"[ \t]*[:][ \t]*([A-Z][a-zA-Z'\-]{1,20}(?:[ \t]+[A-Z][a-zA-Z'\-]{1,20}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _EN),
    # French: "Nom : Dupont", "Prénom : Jean"
    (re.compile(
        r"(?:Nom|Pr[ée]nom|Nom de famille|Nom complet|Identit[ée])"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _FR),
    (re.compile(
        r"(?:Patient|Client|Employ[ée]|Salari[ée]|B[ée]n[ée]ficiaire|"
        r"Assur[ée]|Locataire|Propri[ée]taire|D[ée]fendeur|Demandeur)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _FR),
    # German: "Vorname: Hans"
    (re.compile(
        r"(?:Vorname|Nachname|Familienname|Name)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _DE),
    # Italian: "Nome: Giovanni", "Cognome: Rossi"
    (re.compile(
        r"(?:Nome|Cognome|Nome\s+completo|Nominativo|Intestatario)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _IT),
    (re.compile(
        r"(?:Paziente|Assistito|Assicurato|Inquilino|Proprietario|Richiedente|"
        r"Imputato|Attore|Convenuto|Testimone|Acquirente|Venditore)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _IT),
    # Spanish: "Nombre: García", "Paciente: López Hernández"
    (re.compile(
        r"(?:Nombre|Apellido|Nombre\s+completo)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _ES),
    (re.compile(
        r"(?:Paciente|Cliente|Empleado|Asegurado|Solicitante|Demandante|"
        r"Demandado|Testigo|Comprador|Vendedor|Arrendatario|Propietario)"
        r"[ \t]*[:][ \t]*([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _ES),
    # Dutch: "Naam: de Vries", "Patiënt: Jansen"
    (re.compile(
        r"(?:Naam|Voornaam|Achternaam|Volledige\s+naam)"
        r"[ \t]*[:][ \t]*(?:(?:de|van|den|der|het|ten|ter|te)\s+)*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _NL),
    (re.compile(
        r"(?:Pati[ëe]nt|Cli[ëe]nt|Werknemer|Verzekerde|Aanvrager|"
        r"Gedaagde|Eiser|Getuige|Koper|Verkoper|Huurder|Eigenaar)"
        r"[ \t]*[:][ \t]*(?:(?:de|van|den|der|het|ten|ter|te)\s+)*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _NL),
    # Portuguese: "Nome: Ferreira", "Paciente: Santos"
    (re.compile(
        r"(?:Nome|Apelido|Nome\s+completo)"
        r"[ \t]*[:][ \t]*(?:(?:de|da|do|dos|das)\s+)*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
    ), PIIType.PERSON, 0.85, _PT),
    (re.compile(
        r"(?:Paciente|Cliente|Empregado|Segurado|Requerente|"
        r"R[ée]u|Autor|Testemunha|Comprador|Vendedor|Inquilino|Propriet[áa]rio)"
        r"[ \t]*[:][ \t]*(?:(?:de|da|do|dos|das)\s+)*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}"
        r"(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,20}){0,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _PT),

    # ── Passport after label ──
    (re.compile(
        r"(?:Passport|Passeport|Reisepass|Passaporto|Pasaporte)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([A-Z0-9]{6,9})",
        re.IGNORECASE,
    ), PIIType.PASSPORT, 0.88, _ALL),

    # ── Driver's license after label ──
    (re.compile(
        r"(?:Driver'?s?\s*Licen[cs]e|DL|Permis\s*(?:de\s*)?conduire|"
        r"F[üu]hrerschein|Patente(?:\s*di\s*guida)?|Licencia(?:\s*de\s*conducir)?)"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([A-Z0-9\-]{6,15})",
        re.IGNORECASE,
    ), PIIType.DRIVER_LICENSE, 0.88, _ALL),

    # ── SSN after label ──
    (re.compile(
        r"(?:SSN|Social\s*Security|Tax\s*ID|TIN)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*(\d{3}[-\s]?\d{2}[-\s]?\d{4})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _EN),
    # French SSN after label
    (re.compile(
        r"(?:N°\s*(?:de\s*)?(?:s[ée]curit[ée]\s*sociale|s[ée]cu|SS)|"
        r"Num[ée]ro\s*(?:de\s*)?(?:s[ée]curit[ée]\s*sociale|s[ée]cu|SS)|NIR)"
        r"[ \t]*[:]?[ \t]*([12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|[2-9]\d)\s?\d{2,3}\s?\d{3}\s?\d{3}(?:\s?\d{2})?)",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _FR),
    # UK NI after label
    (re.compile(
        r"(?:National\s*Insurance|NI|NINO)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*"
        r"([A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D])",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _EN),
    # Dutch BSN after label
    (re.compile(
        r"(?:BSN|Burgerservicenummer|Sofinummer)"
        r"[ \t]*(?:No\.?|Number|#|N°)?[ \t]*[:]?[ \t]*(\d{9})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _NL),
    # Portuguese NIF after label
    (re.compile(
        r"(?:NIF|Contribuinte|Número\s*(?:de\s*)?(?:contribuinte|fiscal))"
        r"[ \t]*[:]?[ \t]*([12356789]\d{8})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _PT),
    # Italian Codice Fiscale after label
    (re.compile(
        r"(?:Codice\s*[Ff]iscale|C\.?F\.?)"
        r"[ \t]*[:]?[ \t]*([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _IT),
    # German tax ID after label — Steuer-ID: 12345678901 (11 digits)
    (re.compile(
        r"(?:Steuer-?ID|Steueridentifikationsnummer|Steuernummer|St-?Nr|IdNr)"
        r"[ \t]*[:]?[ \t]*(\d{10,11})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _DE),
    # German social security number — Sozialversicherungsnummer: 12 digits
    (re.compile(
        r"(?:Sozialversicherungsnummer|SV-?Nummer|SVNR|Versicherungsnummer)"
        r"[ \t]*[:]?[ \t]*(\d{2}\s?\d{6}\s?[A-Z]\s?\d{3})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _DE),
    # Spanish DNI/NIE after label
    (re.compile(
        r"(?:DNI|NIE|NIF|Documento\s*(?:Nacional\s*de\s*)?Identidad)"
        r"[ \t]*(?:No\.?|N[°º])?[ \t]*[:]?[ \t]*(\d{8}[A-Z]|[XYZ]\d{7}[A-Z])",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _ES),
    # Spanish Social Security number: 12 digits
    (re.compile(
        r"(?:N[°º]?\s*(?:de\s*)?(?:Seguridad\s*Social|SS|Afiliaci[oó]n))"
        r"[ \t]*[:]?[ \t]*(\d{2}[\s/\-]?\d{8,10}[\s/\-]?\d{2})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _ES),

    # ── IBAN after label ──
    (re.compile(
        r"(?:IBAN|RIB|Compte\s*bancaire|Bankverbindung|Bank\s*[Aa]ccount|Conto\s*corrente)"
        r"[ \t]*[:]?[ \t]*([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,8}(?:\s?[A-Z0-9]{1,4})?)",
        re.IGNORECASE,
    ), PIIType.IBAN, 0.90, _ALL),

    # ── VAT after label ──
    (re.compile(
        r"(?:TVA|VAT|Tax\s*ID|N°\s*TVA|Num[ée]ro\s*(?:de\s*)?TVA|USt-IdNr|NIF|SIREN|SIRET|Partita\s*IVA|P\.?IVA)"
        r"[ \t]*[:]?[ \t]*([A-Z]{0,2}[A-Z0-9]{8,14})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.88, _ALL),

    # ── Address after label ──
    (re.compile(
        r"(?:Address|Adresse|Anschrift|Direcci[oó]n|Indirizzo|Domicile|Domicilio|Residenza)"
        r"[ \t]*[:][ \t]*([^\n\r]{10,80}?)(?=\s*(?:\n|\r|$|(?:Phone|Tel(?:e(?:phone|fon|fax))?|T[ée]l|Mob|Cell|Fax|Facs|Email|Date|Name|Nom|Nome|Cognome)\b))",
        re.IGNORECASE,
    ), PIIType.ADDRESS, 0.80, _ALL),

    # ── Date of birth after label ──
    (re.compile(
        r"(?:Date\s*of\s*Birth|DOB|N[ée]\(?e?\)?\s*le|"
        r"Date\s*de\s*naissance|Geburtsdatum|Geboren\s*am|"
        r"Fecha\s*de\s*nacimiento|Data\s*di\s*nascita)"
        r"[ \t]*[:]?[ \t]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})",
        re.IGNORECASE,
    ), PIIType.DATE, 0.92, _ALL),
    # DOB with verbal month
    (re.compile(
        r"(?:Date\s*of\s*Birth|DOB|N[ée]\(?e?\)?\s*le|Date\s*de\s*naissance)"
        r"[ \t]*[:]?[ \t]*(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    ), PIIType.DATE, 0.90, _ALL),

    # ── Phone after label ──
    (re.compile(
        r"(?:Phone|Tel(?:e(?:phone|fon|fax))?|T[ée]l(?:[ée]ph(?:one)?)?|T[ée]l[ée]c(?:opieur)?|Telex|Facs(?:imile)?|Telec[óo]p(?:ia)?|Mob(?:ile?)?|Cell|Fax|Port(?:able)?|Fixe|Rufn(?:ummer|r)?|Handy)"
        r"\.?"
        r"[ \t]*(?:No\.?|Number|Num[ée]ro|#|N°)?[ \t]*[:]?[ \t]*([\d \t\+\(\)\.\-]{7,20})",
        re.IGNORECASE,
    ), PIIType.PHONE, 0.88, _ALL),

    # ── Email after label ──
    (re.compile(
        r"(?:Email|E-mail|Courriel|Mail)"
        r"[ \t]*[:][ \t]*([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})",
        re.IGNORECASE,
    ), PIIType.EMAIL, 0.95, _ALL),

    # ══════════════════════════════════════════════════════════════════
    # CONTRACT-DOMAIN label-value patterns
    # ══════════════════════════════════════════════════════════════════

    # ── Signatory / signed by ──
    (re.compile(
        r"(?:Signed\s*by|Signature\s*of|Executed\s*by|Authorized\s*by|"
        r"Signé\s*par|Signature\s*de|"
        r"Unterschrieben\s*von|Unterschrift\s*von|"
        r"Firmado\s*por|Firma\s*de|"
        r"Firmato\s*da|Firma\s*di|"
        r"Ondertekend\s*door|Handtekening\s*van|"
        r"Assinado\s*por|Assinatura\s*de)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+(?:de|di|da|van|von|du|del|dos|das)?[ \t]*[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,4})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.88, _ALL),

    # ── Notary names ──
    (re.compile(
        r"(?:Notaire|Notary|Notar(?:in)?|Notaio|Notario|Notaris|Tabelião|Tabeli[ãa]o)"
        r"[ \t]*[:]?[ \t]*"
        r"((?:M[ae]ître|Ma[iî]tre|Me\.?|Dr\.?|Prof\.?)?\s*"
        r"[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.88, _ALL),

    # ── Witness names ──
    (re.compile(
        r"(?:Witness|Témoin|Zeuge|Zeugin|Testigo|Testimone|Getuige|Testemunha)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _ALL),

    # ── Company registration numbers ──
    # SIREN after label
    (re.compile(
        r"(?:SIREN|N[°º]?\s*SIREN|Numéro\s*SIREN|Numero\s*SIREN)"
        r"[ \t]*[:]?[ \t]*(\d{3}\s?\d{3}\s?\d{3})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.92, _FR),
    # SIRET after label
    (re.compile(
        r"(?:SIRET|N[°º]?\s*SIRET|Numéro\s*SIRET|Numero\s*SIRET)"
        r"[ \t]*[:]?[ \t]*(\d{3}\s?\d{3}\s?\d{3}\s?\d{5})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.92, _FR),
    # RCS (Registre du Commerce et des Sociétés) — e.g. "RCS Paris 362 521 879"
    (re.compile(
        r"(?:RCS|R\.C\.S\.)"
        r"[ \t]+([A-ZÀ-Ü][a-zà-ü]+\s+\d{3}\s?\d{3}\s?\d{3})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _FR),
    # HRB / HRA after label
    (re.compile(
        r"(?:Handelsregister|HR|Amtsgericht)"
        r"[ \t]*[:]?[ \t]*((?:[A-ZÀ-Ü][a-zà-ü]+\s+)?HR[AB]\s?\d{3,7}(?:\s?[A-Z])?)",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _DE),
    # Spanish CIF / NIF after label (company)
    (re.compile(
        r"(?:CIF|NIF|C\.I\.F|N\.I\.F)"
        r"[ \t]*[:]?[ \t]*([ABCDEFGHJNPQRSUVW]\d{7}[A-J0-9])",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _ES),
    # Italian Partita IVA after label
    (re.compile(
        r"(?:Partita\s*IVA|P\.?\s*IVA|P\.I\.)"
        r"[ \t]*[:]?[ \t]*(?:IT)?(\d{11})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _IT),
    # UK Companies House number
    (re.compile(
        r"(?:Company\s*(?:Number|No\.?|Registration)|Companies\s*House|Registered\s*No\.?)"
        r"[ \t]*[:]?[ \t]*([A-Z]{0,2}\d{6,8})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.88, _EN),
    # Dutch KvK (Kamer van Koophandel) number
    (re.compile(
        r"(?:KvK|Kamer\s*van\s*Koophandel|KvK-nummer)"
        r"[ \t]*(?:No\.?|Number|Nr\.?|Nummer)?[ \t]*[:]?[ \t]*(\d{8})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _NL),

    # ── BIC/SWIFT after label ──
    (re.compile(
        r"(?:BIC|SWIFT|SWIFT\s*Code|BIC\s*Code|Code\s*BIC|Code\s*SWIFT)"
        r"[ \t]*[:]?[ \t]*([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.92, _ALL),

    # ── Sort Code / Routing Number after label ──
    (re.compile(
        r"(?:Sort\s*Code|Routing\s*(?:Number|No\.?)|ABA)"
        r"[ \t]*[:]?[ \t]*(\d{2}-\d{2}-\d{2}|\d{6}|\d{9})",
        re.IGNORECASE,
    ), PIIType.IBAN, 0.85, _EN),
    # Account Number after label (non-IBAN)
    (re.compile(
        r"(?:Account\s*(?:Number|No\.?|#)|Acct\.?\s*(?:No\.?|#)|"
        r"N[°º]?\s*(?:de\s*)?[Cc]ompte|Kontonummer|Kontonr\.?|"
        r"N[°º]?\s*(?:de\s*)?[Cc]uenta|Numero\s*[Cc]onto|Rekeningnummer)"
        r"[ \t]*[:]?[ \t]*(\d{6,17})",
        re.IGNORECASE,
    ), PIIType.IBAN, 0.80, _ALL),

    # ══════════════════════════════════════════════════════════════════
    # PATIENT / MEDICAL-DOMAIN label-value patterns
    # ══════════════════════════════════════════════════════════════════

    # ── Doctor / Physician names ──
    (re.compile(
        r"(?:Physician|Doctor|Attending|Treating|Referring|"
        r"M[ée]decin(?:\s*traitant)?|Praticien|"
        r"Arzt|[ÄA]rztin|Behandelnder\s*Arzt|"
        r"M[ée]dico|Dottore|Dott\.?(?:ssa)?|"
        r"Arts|Behandelend\s*arts)"
        r"[ \t]*[:]?[ \t]*"
        r"((?:Dr\.?|Prof\.?|Dott\.?(?:ssa)?)\s*"
        r"[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.90, _ALL),

    # ── Hospital / Clinic names ──
    (re.compile(
        r"(?:Hospital|Clinic|Medical\s*Center|Health\s*(?:Centre|Center)|"
        r"H[ôo]pital|Clinique|Centre\s*(?:hospitalier|m[ée]dical)|CHU|"
        r"Krankenhaus|Klinik|Universit[äa]tsklinikum|"
        r"Ospedale|Clinica|Policlinico|"
        r"Ziekenhuis|Kliniek|"
        r"Hospital|Cl[ií]nica|Centro\s*(?:Hospitalar|M[ée]dico))"
        r"[ \t]*[:]?[ \t]*((?:[A-ZÀ-Ü][a-zA-Zà-ü'\-]+\s*){1,6})",
        re.IGNORECASE,
    ), PIIType.ORG, 0.85, _ALL),

    # ── Medical record number after label ──
    (re.compile(
        r"(?:Medical\s*Record\s*(?:Number|No\.?|#)|"
        r"MRN|Patient\s*(?:ID|Number|No\.?|#)|"
        r"Dossier\s*(?:m[ée]dical)?(?:\s*n[°º]?)?|"
        r"N[°º]?\s*(?:de\s*)?dossier(?:\s*m[ée]dical)?|"
        r"Patientenakte|Patientennummer|"
        r"Cartella\s*clinica|N[°º]?\s*cartella|"
        r"Historial(?:\s*cl[ií]nico)?|"
        r"Pati[ëe]ntnummer|Dossiernummer|"
        r"Prontu[áa]rio|Processo\s*cl[ií]nico)"
        r"[ \t]*[:]?[ \t]*([A-Z0-9][\w\-]{3,15})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _ALL),

    # ── Health insurance number after label ──
    (re.compile(
        r"(?:Health\s*Insurance|Insurance\s*(?:Number|No\.?|ID|Policy)|"
        r"(?:Carte\s*)?[Vv]itale|Assurance\s*[Mm]aladie|"
        r"N[°º]?\s*(?:d[e']\s*)?Assur[ée](?:\s*social)?|"
        r"Krankenversichertennummer|Versichertennummer|Kassennummer|"
        r"Krankenkasse(?:nnummer)?|"
        r"Tessera\s*[Ss]anitaria|N[°º]?\s*tessera|"
        r"Tarjeta\s*[Ss]anitaria|N[°º]?\s*(?:de\s*)?afiliaci[oó]n|"
        r"Zorgverzekering(?:snummer)?|Polisnummer|UZOVI|"
        r"N[°º]?\s*(?:de\s*)?[Uu]tente|Cart[ãa]o\s*(?:de\s*)?[Ss]a[úu]de)"
        r"[ \t]*[:]?[ \t]*([A-Z0-9][\w\s\-]{5,25})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.88, _ALL),

    # ── NHS Number after label (UK) ──
    (re.compile(
        r"(?:NHS\s*(?:Number|No\.?|#)|NHS\s*ID)"
        r"[ \t]*[:]?[ \t]*(\d{3}\s?\d{3}\s?\d{4})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _EN),

    # ── German Krankenversichertennummer after label ──
    (re.compile(
        r"(?:Krankenversichertennummer|Versichertennummer|KVNR|Versicherten-Nr)"
        r"[ \t]*[:]?[ \t]*([A-Z]\d{9})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.92, _DE),

    # ── Italian Tessera Sanitaria number after label ──
    (re.compile(
        r"(?:Tessera\s*[Ss]anitaria|N\.?\s*Tessera|Cod(?:ice)?\s*Sanitario)"
        r"[ \t]*[:]?[ \t]*(\d{20}|[A-Z0-9]{10,20})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.88, _IT),

    # ── Emergency contact ──
    (re.compile(
        r"(?:Emergency\s*Contact|Next\s*of\s*Kin|In\s*Case\s*of\s*Emergency|\bICE\b|"
        r"Personne\s*[àa]\s*(?:contacter|pr[ée]venir)|Contact\s*d['\u2019]urgence|"
        r"Notfallkontakt|Kontaktperson|"
        r"Contacto\s*de\s*emergencia|"
        r"Contatto\s*(?:di\s*)?emergenza|"
        r"Noodcontact|Contactpersoon|"
        r"Contacto\s*de\s*emerg[êe]ncia|Pessoa\s*de\s*contacto)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _ALL),

    # ── Blood type / Group (signals patient context, captures nearby name) ──
    # Not PII itself but confirms medical doc context

    # ── Portuguese NISS after label ──
    (re.compile(
        r"(?:NISS|N[°º]?\s*(?:de\s*)?Segurança\s*Social|"
        r"Seguran[çc]a\s*Social(?:\s*n[°º]?)?)"
        r"[ \t]*[:]?[ \t]*(\d{11})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _PT),

    # ── Brazilian CPF after label (PT context) ──
    (re.compile(
        r"(?:CPF|Cadastro\s*(?:de\s*)?Pessoa\s*F[ií]sica)"
        r"[ \t]*[:]?[ \t]*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})",
        re.IGNORECASE,
    ), PIIType.SSN, 0.90, _PT),
    # Brazilian CNPJ after label
    (re.compile(
        r"(?:CNPJ|Cadastro\s*(?:Nacional\s*(?:de\s*)?)?Pessoa\s*Jur[ií]dica)"
        r"[ \t]*[:]?[ \t]*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.90, _PT),

    # ══════════════════════════════════════════════════════════════════
    # FINANCIAL-DOMAIN label-value patterns
    # ══════════════════════════════════════════════════════════════════

    # ── Insurance policy after label ──
    (re.compile(
        r"(?:Policy\s*(?:Number|No\.?|#)|Police\s*(?:d['\u2019]assurance\s*)?(?:n[°º]?)?|"
        r"Policennummer|Polizza|P[oó]liza|Polisnummer|Ap[oó]lice)"
        r"[ \t]*[:]?[ \t]*([A-Z0-9][\w\-]{5,20})",
        re.IGNORECASE,
    ), PIIType.CUSTOM, 0.85, _ALL),

    # ── Beneficiary / Payee names ──
    (re.compile(
        r"(?:Beneficiary|Payee|Pay\s*to(?:\s*the\s*order\s*of)?|"
        r"B[ée]n[ée]ficiaire|Ordre\s*de|"
        r"Beg[üu]nstigter|Zahlungsempf[äa]nger|"
        r"Beneficiario|Destinatario|"
        r"Begunstigde|"
        r"Benefici[áa]rio)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,4})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _ALL),

    # ── Guarantor / Surety names ──
    (re.compile(
        r"(?:Guarantor|Surety|Co-signer|"
        r"Garant|Caution(?:naire)?|"
        r"B[üu]rge|"
        r"Garante|Fideiussore|Fidejussore|"
        r"Borg|"
        r"Fiador|Avalista)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,3})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.85, _ALL),

    # ── Power of Attorney / Representative ──
    (re.compile(
        r"(?:Power\s*of\s*Attorney|Attorney-in-Fact|Legal\s*Representative|"
        r"Mandataire|Repr[ée]sentant(?:\s*l[ée]gal)?|Fond[ée]\s*de\s*pouvoir|"
        r"Bevollm[äa]chtigter|Rechtsvertreter|Vertretungsberechtigt|"
        r"Procuratore|Rappresentante\s*legale|"
        r"Apoderado|Representante\s*legal|"
        r"Gevolmachtigde|Vertegenwoordiger|"
        r"Procurador|Mandatário|Mandat[áa]rio)"
        r"[ \t]*[:]?[ \t]*"
        r"([A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}(?:[ \t]+[A-ZÀ-Ü][a-zA-Zà-ü'\-]{1,25}){1,4})",
        re.IGNORECASE,
    ), PIIType.PERSON, 0.88, _ALL),
]
