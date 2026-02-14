"""Hugging Face BERT-based NER detector — alternative Layer 2 for the hybrid pipeline.

Supports five pre-trained models selectable via config:
  - dslim/bert-base-NER          — general NER (PER, ORG, LOC, MISC)
  - StanfordAIMI/stanford-deidentifier-base — clinical / medical de-identification
  - lakshyakh93/deberta_finetuned_pii       — PII-specific (names, emails, phones, etc.)
  - iiiorg/piiranha-v1-detect-personal-information — multilingual PII (93% F1, 6 languages)
  - Isotonic/distilbert_finetuned_ai4privacy_v2    — fast PII (95% F1, 54 entity types)

Texts are processed in overlapping chunks so accuracy stays high for long
documents.  The public API mirrors ``ner_detector`` so the pipeline can
swap between spaCy and BERT transparently.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple, Optional

from models.schemas import PIIType

logger = logging.getLogger(__name__)


class NERMatch(NamedTuple):
    start: int
    end: int
    text: str
    pii_type: PIIType
    confidence: float


# ---------------------------------------------------------------------------
# Supported models and their entity-label → PIIType mappings
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: dict[str, dict] = {
    "dslim/bert-base-NER": {
        "description": "General NER (PER, ORG, LOC, MISC) — lightweight, fast",
        "label_map": {
            "PER": PIIType.PERSON,
            "ORG": PIIType.ORG,
            "LOC": PIIType.LOCATION,
            "MISC": PIIType.CUSTOM,
        },
    },
    "StanfordAIMI/stanford-deidentifier-base": {
        "description": "Clinical / medical de-identification",
        "label_map": {
            "PATIENT": PIIType.PERSON,
            "STAFF": PIIType.PERSON,
            "AGE": PIIType.DATE,
            "DATE": PIIType.DATE,
            "PHONE": PIIType.PHONE,
            "ID": PIIType.CUSTOM,
            "EMAIL": PIIType.EMAIL,
            "PATORG": PIIType.ORG,
            "HOSPITAL": PIIType.ORG,
            "OTHERPHI": PIIType.CUSTOM,
            "LOC": PIIType.LOCATION,
            "LOCATION": PIIType.LOCATION,
            "HCW": PIIType.PERSON,
            "VENDOR": PIIType.ORG,
        },
    },
    "lakshyakh93/deberta_finetuned_pii": {
        "description": "PII-specific (names, emails, phones, addresses, etc.)",
        "label_map": {
            "NAME_STUDENT": PIIType.PERSON,
            "EMAIL": PIIType.EMAIL,
            "USERNAME": PIIType.PERSON,
            "ID_NUM": PIIType.CUSTOM,
            "PHONE_NUM": PIIType.PHONE,
            "URL_PERSONAL": PIIType.CUSTOM,
            "STREET_ADDRESS": PIIType.ADDRESS,
        },
    },
    # -- Multilingual PII (mDeBERTa-v3-base, 0.3B params) -----------------
    # 93% F1 · 98% PII recall · EN/ES/FR/DE/IT/NL
    "iiiorg/piiranha-v1-detect-personal-information": {
        "description": "Piiranha — multilingual PII (93% F1, EN/ES/FR/DE/IT/NL)",
        "label_map": {
            "GIVENNAME": PIIType.PERSON,
            "SURNAME": PIIType.PERSON,
            "EMAIL": PIIType.EMAIL,
            "TELEPHONENUM": PIIType.PHONE,
            "CREDITCARDNUMBER": PIIType.CREDIT_CARD,
            "SOCIALNUM": PIIType.SSN,
            "DATEOFBIRTH": PIIType.DATE,
            "DRIVERLICENSENUM": PIIType.DRIVER_LICENSE,
            "STREET": PIIType.ADDRESS,
            "CITY": PIIType.ADDRESS,
            "ZIPCODE": PIIType.ADDRESS,
            "BUILDINGNUM": PIIType.ADDRESS,
            "ACCOUNTNUM": PIIType.CUSTOM,
            "IDCARDNUM": PIIType.PASSPORT,
            "TAXNUM": PIIType.CUSTOM,
            "PASSWORD": PIIType.CUSTOM,
            "USERNAME": PIIType.PERSON,
        },
    },
    # -- Fast PII (DistilBERT, 66M params) ---------------------------------
    # 95% F1 · 54 entity types · English-focused
    "Isotonic/distilbert_finetuned_ai4privacy_v2": {
        "description": "DistilBERT AI4Privacy — fast PII (95% F1, 54 entity types)",
        "label_map": {
            # Names
            "Firstname": PIIType.PERSON,
            "Lastname": PIIType.PERSON,
            "Middlename": PIIType.PERSON,
            "Prefix": PIIType.PERSON,
            "Username": PIIType.PERSON,
            # Contact
            "Email": PIIType.EMAIL,
            "Phonenumber": PIIType.PHONE,
            "Phoneimei": PIIType.PHONE,
            "Url": PIIType.CUSTOM,
            # Financial
            "Creditcardnumber": PIIType.CREDIT_CARD,
            "Creditcardcvv": PIIType.CREDIT_CARD,
            "Creditcardissuer": PIIType.CREDIT_CARD,
            "Iban": PIIType.IBAN,
            "Bic": PIIType.CUSTOM,
            "Accountname": PIIType.CUSTOM,
            "Accountnumber": PIIType.CUSTOM,
            "Pin": PIIType.CUSTOM,
            "Maskednumber": PIIType.CUSTOM,
            # Identity
            "Ssn": PIIType.SSN,
            "Date": PIIType.DATE,
            "Dob": PIIType.DATE,
            "Password": PIIType.CUSTOM,
            # Address / Location
            "Street": PIIType.ADDRESS,
            "Buildingnumber": PIIType.ADDRESS,
            "Secondaryaddress": PIIType.ADDRESS,
            "Zipcode": PIIType.ADDRESS,
            "City": PIIType.ADDRESS,
            "State": PIIType.ADDRESS,
            "County": PIIType.ADDRESS,
            "Nearbygpscoordinate": PIIType.LOCATION,
            # Organization
            "Companyname": PIIType.ORG,
            # Network / Tech
            "Ip": PIIType.IP_ADDRESS,
            "Ipv4": PIIType.IP_ADDRESS,
            "Ipv6": PIIType.IP_ADDRESS,
            "Mac": PIIType.CUSTOM,
            "Useragent": PIIType.CUSTOM,
            # Crypto
            "Bitcoinaddress": PIIType.CUSTOM,
            "Ethereumaddress": PIIType.CUSTOM,
            "Litecoinaddress": PIIType.CUSTOM,
            # Vehicle
            "Vehiclevin": PIIType.CUSTOM,
            "Vehiclevrm": PIIType.CUSTOM,
            # Jobs (low PII value but model detects them)
            "Jobtitle": PIIType.CUSTOM,
            "Jobarea": PIIType.CUSTOM,
            "Jobtype": PIIType.CUSTOM,
        },
    },
}

# ---------------------------------------------------------------------------
# False-positive filters
# ---------------------------------------------------------------------------

# Words that BERT models frequently misclassify as PERSON.
# Covers all four supported languages (EN/FR/IT/DE).
_PERSON_NOISE: set[str] = {
    # English
    "the", "a", "an", "this", "that", "it", "i", "we", "you", "he", "she",
    "my", "your", "his", "her", "our", "their", "its",
    "mr", "mrs", "ms", "dr", "prof",
    "dear", "hi", "hello", "yes", "no", "ok", "please", "thank", "thanks",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "page", "section", "table", "figure", "chapter", "appendix",
    "total", "amount", "balance", "date", "number", "type",
    "note", "notes", "net", "tax", "other", "non",
    # English job titles / roles
    "chairman", "chairwoman", "chairperson", "chair",
    "president", "vice", "director", "officer", "manager",
    "chief", "executive", "ceo", "cfo", "coo", "cto", "cio",
    "secretary", "treasurer", "counsel", "attorney",
    "partner", "associate", "analyst", "consultant",
    "md", "svp", "evp", "vp",
    "head", "lead", "senior", "junior",
    # English generic business terms
    "q1", "q2", "q3", "q4", "fy", "ytd", "mtd",
    "n/a", "na", "tbd", "tba", "etc", "pdf", "doc",
    "inc", "llc", "ltd", "corp",
    "quarterly", "annual", "monthly", "weekly", "daily",
    "next", "last", "previous", "current", "recent",
    "today", "tomorrow", "yesterday",
    "above", "below", "subtotal", "grand",
    # English accounting / financial terms often tagged PERSON
    "assets", "asset", "liabilities", "liability", "equity",
    "revenue", "revenues", "expenses", "expense", "income",
    "profit", "loss", "cash", "capital", "debt",
    "depreciation", "amortization", "provision", "provisions",
    "interest", "dividend", "dividends",
    "current", "long", "short", "term",
    "goodwill", "inventory", "receivable", "receivables",
    "payable", "payables", "deferred", "retained",
    "earnings", "cost", "costs", "margin", "surplus", "deficit",
    # French
    "monsieur", "madame", "mademoiselle", "mme", "mlle",
    "le", "la", "les", "un", "une", "des", "du", "de",
    "ce", "cette", "son", "sa", "ses", "notre", "votre", "leur",
    "il", "elle", "nous", "vous", "ils", "elles", "on",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre",
    "décembre", "decembre",
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
    "qui", "que", "où", "ou", "quoi", "dont", "avec", "sans", "pour", "par",
    "dans", "sur", "sous", "vers", "chez", "dès",
    "actif", "passif", "actifs", "passifs",
    "court", "long", "terme",
    "encaisse", "immobilisations", "immobilisation",
    "amortissement", "emprunt", "solde",
    "résultat", "resultat", "résultats", "resultats",
    "bénéfice", "benefice", "perte", "pertes",
    "bilan", "exercice", "exercices",
    "charges", "produits", "compte", "comptes",
    "société", "societe", "entreprise",
    "principales", "principaux", "principale", "principal",
    "général", "generale", "generaux",
    "comptables", "comptable", "financier", "financiere",
    # Italian
    "signor", "signore", "signora", "signorina", "sig", "dott", "avv",
    "attivo", "passivo", "bilancio", "esercizio",
    # German
    "herr", "frau",
}

# Regex to check if text is purely numeric / punctuation (no real name)
_DIGITS_ONLY_RE = re.compile(r"^[\d\s\.,;:\-/]+$")

# ---------------------------------------------------------------------------
# ORG false-positive filter
# ---------------------------------------------------------------------------

_ORG_NOISE: set[str] = {
    # English generic business / accounting / legal terms
    "department", "section", "division", "group", "team",
    "committee", "board", "council", "commission",
    "act", "law", "regulation", "policy", "standard",
    "agreement", "contract", "report", "summary",
    "schedule", "exhibit", "annex", "appendix",
    "article", "clause", "provision", "amendment",
    "table", "figure", "chart", "graph", "page",
    "total", "subtotal", "grand", "amount", "balance",
    "net", "tax", "note", "notes", "other", "non",
    "assets", "asset", "liabilities", "liability", "equity",
    "revenue", "revenues", "expenses", "expense", "income",
    "profit", "loss", "cash", "capital", "debt",
    "depreciation", "amortization", "provision", "provisions",
    "interest", "dividend", "dividends",
    "goodwill", "inventory", "receivable", "receivables",
    "payable", "payables", "deferred", "retained",
    "earnings", "cost", "costs", "margin", "surplus", "deficit",
    "current", "long", "short", "term",
    "quarterly", "annual", "monthly", "weekly", "daily",
    "q1", "q2", "q3", "q4", "fy", "ytd", "mtd",
    "inc", "llc", "ltd", "corp", "co", "plc", "sa", "se",
    # French accounting / business / legal terms
    "société", "societe", "entreprise", "compagnie", "filiale",
    "département", "departement", "service", "bureau", "direction",
    "division", "commission", "comité", "comite",
    "conseil", "ministère", "ministere", "gouvernement",
    "article", "clause", "alinéa", "alinea", "annexe",
    "tableau", "graphique",
    "loi", "décret", "decret", "arrêté", "arrete", "règlement", "reglement",
    "contrat", "accord", "convention", "rapport", "résumé", "resume",
    "actif", "passif", "actifs", "passifs",
    "court", "long", "terme",
    "encaisse", "emprunt", "immobilisation", "immobilisations",
    "amortissement", "solde",
    "résultat", "resultat", "résultats", "resultats",
    "bénéfice", "benefice", "perte", "pertes",
    "bilan", "exercice", "exercices",
    "charges", "produits", "compte", "comptes",
    "exploitation", "financement", "investissement",
    "achats", "coût", "cout", "frais",
    "client", "fournisseur",
    "principales", "principaux", "principale", "principal",
    "général", "generale", "generaux", "générale", "généraux",
    "comptables", "comptable", "comptabilité", "comptabilite",
    "financier", "financiere", "financiers", "financieres",
    "financière", "financières",
    "corporelles", "corporels", "corporel", "corporelle",
    "méthodes", "methodes", "méthode", "methode",
    "statuts", "statut", "nature",
    "activités", "activites", "activité", "activite",
    "éléments", "elements", "élément", "element",
    "informations", "information",
    "établissement", "etablissement", "établissements", "etablissements",
    "opérations", "operations", "opération", "operation",
    "complémentaires", "complementaires", "complémentaire", "complementaire",
    "notes", "note",
    "appliquée", "applique", "appliquées", "appliques",
    "appliqué", "appliqués",
    "groupe", "section",
    # French document headings / generic descriptive words (never org names)
    "renseignements", "complémentaires", "complementaires",
    "sommaire", "introduction", "conclusion", "observations",
    "vérification", "verification", "certification", "attestation",
    "présentation", "presentation", "description", "recommandations",
    "recommandation", "constatations", "constatation",
    "objectifs", "objectif", "mandat", "portée", "portee",
    "responsabilités", "responsabilites", "responsabilité", "responsabilite",
    "états", "etats", "état", "etat",
    "résultats", "resultats", "résultat", "resultat",
    "auditeurs", "auditeur", "auditrice", "auditrices",
    "générales", "generales", "particulières", "particulieres",
    "supplémentaires", "supplementaires", "relatives", "relatifs",
    "aux", "sur", "des", "les", "par",
    # English document headings / generic descriptive words
    "additional", "supplementary", "complementary", "preliminary",
    "consolidated", "independent", "overview", "background",
    "disclosures", "disclosure", "requirements", "requirement",
    "management", "discussion", "analysis", "review",
    "assessment", "evaluation", "examination", "verification",
    "certification", "statement", "statements", "financial",
    "auditors", "auditor", "general", "specific",
    # Partial short terms
    "fr", "emp", "lo", "en", "per", "ex", "amor", "immob",
    "fourn", "four",
    # Italian
    "dipartimento", "servizio", "ufficio", "direzione",
    "sezione", "articolo", "clausola", "allegato", "grafico",
    "legge", "decreto", "ordinanza", "regolamento",
    "contratto", "accordo", "convenzione", "rapporto", "relazione",
    # German
    "gesellschaft", "unternehmen", "abteilung",
    # Spanish
    "empresa", "compañía", "compania", "división",
}


def _is_org_noise(text: str) -> bool:
    """Return True if a BERT ORG entity is likely a false positive."""
    clean = text.strip()
    low = clean.lower()

    # Single stopword
    if low in _ORG_NOISE:
        return True
    # Too short (≤2 chars)
    if len(clean) <= 2:
        return True
    # All-uppercase and very short (e.g. "SA", "TVA", "BN")
    if clean.isupper() and len(clean) <= 4:
        return True
    # Pure digits / punctuation
    if _DIGITS_ONLY_RE.match(clean):
        return True
    # Starts with a digit — not an org name
    # EXCEPT numbered company patterns (e.g., "9169270 Canada inc.")
    if clean and clean[0].isdigit():
        from core.detection.noise_filters import has_legal_suffix
        if not has_legal_suffix(clean):
            return True
    # All-lowercase — real org names are capitalised
    words = clean.split()
    if clean == clean.lower() and len(words) <= 2:
        return True
    # Single very short word (≤3 chars)
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    # Multi-word: every word is a noise term → not a real org
    if len(words) >= 2 and all(w.lower() in _ORG_NOISE for w in words):
        return True
    return False


def _is_person_noise(text: str) -> bool:
    """Return True if a BERT PERSON entity is likely a false positive."""
    clean = text.strip()
    low = clean.lower()

    # Single stopword
    if low in _PERSON_NOISE:
        return True
    # All-uppercase and very short (e.g. "TVA", "BN", "SA")
    if clean.isupper() and len(clean) <= 5:
        return True
    # Starts with a digit — not a name
    if clean and clean[0].isdigit():
        return True
    # Pure digits / punctuation
    if _DIGITS_ONLY_RE.match(clean):
        return True
    # Single very short word (≤3 chars)
    words = clean.split()
    if len(words) == 1 and len(words[0]) <= 3:
        return True
    # Multi-word: every word is a stopword → noise
    if len(words) >= 2 and all(w.lower() in _PERSON_NOISE for w in words):
        return True
    # All-lowercase text — real names are capitalised
    if clean == clean.lower() and len(words) <= 3:
        return True
    return False


# ---------------------------------------------------------------------------
# Module-level state (lazy-loaded)
# ---------------------------------------------------------------------------

_pipeline = None
_active_model_id: str = ""
_label_map: dict[str, PIIType] = {}

# Chunking parameters
_CHUNK_SIZE = 2_500        # characters per chunk (BERT tokeniser limit ~512 tokens ≈ 2-3k chars)
_CHUNK_OVERLAP = 300       # overlap in characters


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_pipeline(model_id: str | None = None) -> object:
    """Lazy-load a Hugging Face token-classification pipeline."""
    global _pipeline, _active_model_id, _label_map

    if model_id is None or model_id == "auto":
        from core.config import config
        if config.ner_backend not in ("spacy", "auto"):
            model_id = config.ner_backend
        else:
            # Default fallback — auto mode should resolve before calling here
            model_id = "Isotonic/distilbert_finetuned_ai4privacy_v2"

    if _pipeline is not None and _active_model_id == model_id:
        return _pipeline

    from transformers import pipeline as hf_pipeline

    logger.info(f"Loading HF NER model '{model_id}' …")
    model_info = AVAILABLE_MODELS.get(model_id)
    if model_info is None:
        raise ValueError(
            f"Unknown BERT NER model '{model_id}'. "
            f"Available: {', '.join(AVAILABLE_MODELS)}"
        )

    _pipeline = hf_pipeline(
        "ner",
        model=model_id,
        aggregation_strategy="simple",
        device=-1,                    # CPU; set 0 for GPU
    )
    _active_model_id = model_id
    _label_map = model_info["label_map"]
    logger.info(f"HF model '{model_id}' loaded successfully")
    return _pipeline


def unload_pipeline() -> None:
    """Free memory held by the current HF model."""
    global _pipeline, _active_model_id, _label_map
    _pipeline = None
    _active_model_id = ""
    _label_map = {}
    logger.info("HF NER pipeline unloaded")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _process_chunk(pipe, text: str, global_offset: int) -> list[NERMatch]:
    """Run the HF pipeline on a single chunk and yield NERMatch instances."""
    results = pipe(text)
    matches: list[NERMatch] = []

    for ent in results:
        # ``aggregation_strategy="simple"`` gives keys:
        #   entity_group, score, word, start, end
        raw_label: str = ent.get("entity_group", "")
        score: float = ent.get("score", 0.0)
        start: int = ent.get("start", 0)
        end: int = ent.get("end", 0)
        word: str = ent.get("word", text[start:end])

        pii_type = _label_map.get(raw_label)
        if pii_type is None:
            continue
        if len(word.strip()) < 2:
            continue

        # Filter PERSON false positives (stopwords, digits, short tokens, etc.)
        if pii_type == PIIType.PERSON and _is_person_noise(word):
            continue

        # Filter ORG false positives (accounting terms, generic business words, etc.)
        if pii_type == PIIType.ORG and _is_org_noise(word):
            continue

        matches.append(NERMatch(
            start=global_offset + start,
            end=global_offset + end,
            text=word,
            pii_type=pii_type,
            confidence=round(score, 4),
        )) 

    return matches


def _deduplicate_matches(matches: list[NERMatch], source_text: str = "") -> list[NERMatch]:
    """Remove duplicates arising from overlapping chunks and merge
    adjacent ADDRESS fragments into one region."""
    if not matches:
        return []

    matches = sorted(matches, key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[NERMatch] = [matches[0]]

    for m in matches[1:]:
        prev = deduped[-1]
        if m.start < prev.end:
            if m.confidence > prev.confidence or (m.end - m.start) > (prev.end - prev.start):
                deduped[-1] = m
        else:
            deduped.append(m)

    # Merge adjacent ADDRESS fragments (STREET + CITY + BUILDINGNUM + ZIPCODE)
    # that sit close together.  Also absorb LOCATION entities sandwiched
    # between two ADDRESS entities (city / state names).
    merged: list[NERMatch] = [deduped[0]] if deduped else []
    for m in deduped[1:]:
        prev = merged[-1]
        can_merge = False
        if prev.pii_type == PIIType.ADDRESS and m.pii_type in (PIIType.ADDRESS, PIIType.LOCATION):
            can_merge = True
        elif prev.pii_type == PIIType.ADDRESS and m.pii_type != PIIType.ADDRESS:
            # Check if this non-ADDRESS is sandwiched — peek ahead handled by
            # absorbing LOCATION into ADDRESS, so next iteration chain continues.
            pass
        if can_merge:
            gap = m.start - prev.end
            if 0 <= gap <= 50:
                best_conf = max(prev.confidence, m.confidence)
                # Rebuild text from source if available, else concatenate
                if source_text:
                    combined_text = source_text[prev.start:m.end]
                else:
                    combined_text = prev.text + " " + m.text
                merged[-1] = NERMatch(
                    start=prev.start,
                    end=m.end,
                    text=combined_text,
                    pii_type=PIIType.ADDRESS,
                    confidence=best_conf,
                )
                continue
        merged.append(m)

    return merged


def detect_bert_ner(text: str, model_id: str | None = None) -> list[NERMatch]:
    """
    Run Hugging Face BERT NER on *text* and return PII matches.

    Long texts are split into overlapping chunks to stay within the
    model's context window.
    """
    pipe = _load_pipeline(model_id)

    if len(text) <= _CHUNK_SIZE:
        # Single chunk — still run dedup/ADDRESS-merge pass
        return _deduplicate_matches(
            _process_chunk(pipe, text, global_offset=0),
            source_text=text,
        )

    all_matches: list[NERMatch] = []
    offset = 0
    while offset < len(text):
        end = min(offset + _CHUNK_SIZE, len(text))
        chunk = text[offset:end]
        chunk_matches = _process_chunk(pipe, chunk, global_offset=offset)
        all_matches.extend(chunk_matches)

        offset += _CHUNK_SIZE - _CHUNK_OVERLAP
        if end == len(text):
            break

    return _deduplicate_matches(all_matches, source_text=text)


# ---------------------------------------------------------------------------
# Introspection helpers (used by API / settings)
# ---------------------------------------------------------------------------

def get_active_model_id() -> str:
    """Return the currently loaded HF model id, or ``""``."""
    return _active_model_id


def is_bert_ner_available() -> bool:
    """Check if a BERT NER pipeline can be loaded (transformers installed)."""
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def list_available_bert_models() -> list[dict]:
    """Return metadata for all supported BERT NER models."""
    return [
        {"model_id": mid, "description": info["description"]}
        for mid, info in AVAILABLE_MODELS.items()
    ]
