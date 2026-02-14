"""Pipeline-level noise word sets and predicate functions.

Centralises all noise filtering logic so that pipeline, merge, and
propagation modules share a single definition.
"""

from __future__ import annotations

import re as _re
from typing import Set

from models.schemas import PIIType

# ---------------------------------------------------------------------------
# Legal-suffix regex — shared across all noise filters
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_RE: _re.Pattern[str] = _re.compile(
    r'\b(?:inc|corp|ltd|llc|llp|plc|co|lp|sas|sarl|gmbh|ag|bv|nv|'
    r'lt[ée]e|limit[ée]e|enr|s\.?e\.?n\.?c\.?|'
    r's\.?a\.?r?\.?l?\.?|s\.?p\.?a\.?|s\.?r\.?l\.?)\b\.?',
    _re.IGNORECASE,
)


def has_legal_suffix(text: str) -> bool:
    """Return True if *text* contains a legal company suffix anywhere."""
    return bool(LEGAL_SUFFIX_RE.search(text.strip()))


# ── ORG noise ─────────────────────────────────────────────────────────────

_ORG_PIPELINE_NOISE: Set[str] = {
    # English
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
    "inc", "llc", "ltd", "corp", "co", "plc", "sa", "se",
    # French
    "société", "societe", "entreprise", "compagnie", "filiale",
    "département", "departement", "service", "bureau", "direction",
    "division", "commission", "comité", "comite",
    "conseil", "ministère", "ministere", "gouvernement",
    "article", "clause", "alinéa", "alinea", "annexe",
    "tableau", "graphique",
    "loi", "décret", "decret", "arrêté", "arrete",
    "règlement", "reglement",
    "contrat", "accord", "convention", "rapport",
    "résumé", "resume",
    "actif", "passif", "actifs", "passifs",
    "court", "long", "terme",
    "encaisse", "emprunt", "immobilisation", "immobilisations",
    "amortissement", "solde",
    "résultat", "resultat", "résultats", "resultats",
    "bénéfice", "benefice", "perte", "pertes",
    "bilan", "exercice", "exercices", "clos", "clôt",
    "excédent", "excedent", "excédents", "excedents",
    "norme", "normes", "canadienne", "canadiennes", "canadien", "canadiens",
    "charges", "produits", "compte", "comptes",
    "exploitation", "financement", "investissement",
    "achats", "coût", "cout", "frais",
    "client", "fournisseur",
    "taux", "location", "acquisition", "acquisitions",
    "location-acquisition", "lave-vaisselle",
    "dotation", "dotations", "reprise", "reprises",
    "écart", "ecart", "écarts", "ecarts",
    "valeur", "valeurs", "emprunt", "emprunts",
    "titre", "titres", "fonds", "caisse",
    "trésorerie", "tresorerie",
    "recette", "recettes", "facture", "factures",
    "poste", "postes", "créance", "creance", "créances", "creances",
    "dette", "dettes", "subvention", "subventions",
    "cra", "senc", "osbl", "obnl",
    "fournitures", "fourniture",
    "instruments", "instrument",
    "créances", "creances", "créance", "creance",
    "douteuses", "douteuse", "douteux",
    "catégorie", "categorie", "catégories", "categories",
    "mère", "mere",
    "consolidés", "consolides", "consolidé", "consolide",
    "organisme", "organismes",
    "préparation", "preparation", "préparations", "preparations",
    "renouvellement", "renouvellements",
    "complexe", "nautique",
    "équipements", "equipements", "équipement", "equipement",
    "matériel", "materiel", "matériels", "materiels",
    "informatique", "informatiques",
    "installation", "installations",
    "réservoirs", "reservoirs", "réservoir", "reservoir",
    "pontons", "ponton", "quai", "quais",
    "bâtiment", "batiment", "bâtiments", "batiments",
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
    "établissement", "etablissement",
    "établissements", "etablissements",
    "opérations", "operations", "opération", "operation",
    "complémentaires", "complementaires",
    "complémentaire", "complementaire",
    "renseignements",
    "sommaire", "introduction", "conclusion", "observations",
    "vérification", "verification", "certification", "attestation",
    "présentation", "presentation", "description", "recommandations",
    "recommandation", "constatations", "constatation",
    "objectifs", "objectif", "mandat", "portée", "portee",
    "responsabilités", "responsabilites", "responsabilité", "responsabilite",
    "états", "etats", "état", "etat",
    "auditeurs", "auditeur", "auditrice", "auditrices",
    "générales", "generales", "particulières", "particulieres",
    "supplémentaires", "supplementaires", "relatives", "relatifs",
    "aux", "sur", "des", "les", "par",
    "additional", "supplementary", "complementary", "preliminary",
    "consolidated", "independent", "overview", "background",
    "disclosures", "disclosure", "requirements", "requirement",
    "management", "discussion", "analysis", "review",
    "assessment", "evaluation", "examination",
    "statement", "statements", "financial",
    "auditors", "auditor", "general", "specific",
    "notes", "note",
    "groupe", "section",
    "société", "societe",
    # Italian
    "dipartimento", "servizio", "ufficio", "direzione",
    "sezione", "articolo", "clausola", "allegato", "grafico",
    "legge", "decreto", "ordinanza", "regolamento",
    "contratto", "accordo", "convenzione",
    "rapporto", "relazione",
    # German / Spanish
    "gesellschaft", "unternehmen", "abteilung",
    "empresa", "compañía", "compania", "división",
}


def _is_org_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy ORG false-positive."""
    clean = text.strip()
    low = clean.lower()
    if low in _ORG_PIPELINE_NOISE:
        return True
    _stripped = _re.sub(r"^[LlDd]['\u2019]\s*", "", clean)
    if _stripped and _stripped.lower() in _ORG_PIPELINE_NOISE:
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
    if len(words) >= 2 and all(
        w.lower() in _ORG_PIPELINE_NOISE
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
    ):
        return True
    if len(words) == 2 and words[0].lower() == "portion" and words[1].isdigit():
        return True
    if len(words) == 2 and words[0].lower() in (
        "le", "la", "les", "de", "du", "des", "au", "aux", "un", "une"
    ) and words[1].isupper() and len(words[1]) >= 2:
        return True
    if len(words) >= 2 and words[0].lower() in ("société", "societe"):
        w1 = words[1].lower()
        _sentence_verbs = {
            "et", "ou", "qui", "que", "est", "a", "sont", "ont", "peut", "doit",
            "détermine", "determine", "présente", "presente", "utilise", "applique",
            "établit", "etablit", "calcule", "comptabilise", "reconnaît", "reconnait",
            "constate", "enregistre", "amortit", "provisionne", "rembourse",
            "détient", "detient", "possède", "possede", "gère", "gere",
            "exploite", "opère", "opere", "emploie", "embauche",
            "vend", "achète", "achete", "loue", "fabrique", "produit",
            "offre", "fournit", "distribue", "exporte", "importe",
        }
        if w1 in _sentence_verbs:
            return True
    if len(words) >= 3 and words[1].lower() in ("est", "a", "sont", "ont", "peut", "doit"):
        return True
    if "pour" in [w.lower() for w in words]:
        return True
    if len(words) >= 3:
        low_words = [w.lower() for w in words]
        if "catégorie" in low_words or "categorie" in low_words:
            return True
    return False


# ── LOCATION noise ────────────────────────────────────────────────────────

_LOC_PIPELINE_NOISE: Set[str] = {
    "complexe", "nautique", "piscine", "gymnase",
    "terrain", "terrains",
    "bâtiment", "batiment", "bâtiments", "batiments",
    "local", "locaux",
    "salle", "salles",
    "atelier", "ateliers",
    "entrepôt", "entrepot", "entrepôts", "entrepots",
    "hangar", "hangars",
    "garage", "garages",
    "parking", "parkings",
    "usine", "usines",
    "magasin", "magasins",
    "mobilier", "immobilier",
    "corporel", "corporels", "corporelle", "corporelles",
    "incorporel", "incorporels", "incorporelle", "incorporelles",
    "immobilisation", "immobilisations",
    "exploitation", "investissement", "financement",
    "trésorerie", "tresorerie",
    "stock", "stocks",
    "taux", "montant", "solde",
    "actif", "passif", "bilan",
    "amortissement", "amortissements",
    "dotation", "dotations",
    "provision", "provisions",
    "emprunt", "emprunts",
    "résultat", "resultat", "résultats", "resultats",
    "page", "section", "chapitre", "annexe", "tableau",
    "total", "note", "notes",
    "building", "buildings", "facility", "facilities",
    "warehouse", "workshop", "premises",
    "complex", "pool", "gymnasium",
    "furniture", "equipment",
}


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
    words = clean.split()
    if len(words) >= 2 and all(
        w.lower() in _LOC_PIPELINE_NOISE
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
    ):
        return True
    return False


# ── PERSON noise ──────────────────────────────────────────────────────────

_PERSON_PIPELINE_NOISE: Set[str] = {
    "mobilier", "immobilier",
    "taux", "montant", "solde", "bilan",
    "bénéfice", "benefice", "bénéfices", "benefices",
    "revenus", "revenu",
    "nette", "net", "nets", "nettes",
    "intérêts", "interets", "intérêt", "interet",
    "gain", "gains",
    "coûts", "couts", "coût", "cout",
    "honoraires", "honoraire",
    "loyers", "loyer",
    "salaires", "salaire",
    "impôts", "impots", "impôt", "impot",
    "taxes", "taxe",
    "dividendes", "dividende",
    "exercice", "résultat", "resultat",
    "actif", "passif", "capital",
    "emprunt", "crédit", "credit", "débit", "debit",
    "amortissement", "amortissements",
    "provision", "provisions",
    "dotation", "dotations",
    "reprise", "reprises",
    "charge", "charges", "produit", "produits",
    "recette", "recettes", "dépense", "depense", "dépenses", "depenses",
    "facture", "factures",
    "titre", "titres",
    "fonds", "caisse",
    "valeur", "valeurs",
    "compte", "comptes",
    "poste", "postes",
    "dette", "dettes",
    "subvention", "subventions",
    "trésorerie", "tresorerie",
    "location", "acquisition", "acquisitions",
    "location-acquisition", "lave-vaisselle",
    "clos", "clôt",
    "retenue", "retenues",
    "prélèvement", "prelevement", "prélèvements", "prelevements",
    "lecteur", "lectrice", "lecteurs", "lectrices",
    "utilisateur", "utilisatrice", "destinataire",
    "corporel", "corporels", "corporelle", "corporelles",
    "incorporel", "incorporels", "incorporelle", "incorporelles",
    "courant", "courants", "courante", "courantes",
    "financier", "financiere", "financiers", "financieres",
    "financière", "financières",
    "comptable", "comptables",
    "page", "section", "chapitre", "annexe", "tableau",
    "total", "note", "notes",
    "introduction", "conclusion", "sommaire",
    "balance", "income", "expense", "revenue", "profit", "loss",
    "asset", "assets", "rate", "amount",
    "depreciation", "amortization",
    "fund", "funds", "account", "accounts",
    "furniture", "equipment",
}


def _is_person_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy PERSON false-positive."""
    clean = text.strip()
    low = clean.lower()
    if low in _PERSON_PIPELINE_NOISE:
        return True
    stripped = _re.sub(r"^(?:[Ll][ea]s?|[Dd][ue]s?|[Uu]n[e]?|[Ll]['']|[Dd][''])\s*", "", clean)
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
    if len(words) >= 2 and all(
        _is_org_pipeline_noise(w) or w.lower() in _PERSON_PIPELINE_NOISE
        for w in words
    ):
        return True
    return False


# ── ADDRESS number-only filter ────────────────────────────────────────────

_ADDR_ALPHA_RE = _re.compile(r"[A-Za-zÀ-ÿ]")
_ADDR_DIGIT_RE = _re.compile(r"\d")


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
    _mortgage_terms = (
        "hypothécaire", "hypothecaire", "hypothèque", "hypotheque",
        "remboursable", "remboursement", "remboursements",
        "mensuel", "mensuels", "mensuelle", "mensuelles",
        "trimestriel", "trimestriels", "trimestrielle", "trimestrielles",
        "annuel", "annuels", "annuelle", "annuelles",
        "échéance", "echeance", "échéances", "echeances",
        "capital", "intérêt", "interet", "intérêts", "interets",
        "emprunt", "emprunts", "prêt", "pret", "prêts", "prets",
        "créancier", "creancier", "débiteur", "debiteur",
    )
    for term in _mortgage_terms:
        if term in low:
            return True
    return False


# ── Structured type minimum digit counts ──────────────────────────────────

_STRUCTURED_MIN_DIGITS: dict[PIIType, int] = {
    PIIType.PHONE: 7,
    PIIType.SSN: 7,
    PIIType.DRIVER_LICENSE: 6,
}
