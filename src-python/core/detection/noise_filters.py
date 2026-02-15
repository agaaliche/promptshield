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
from pathlib import Path
from typing import Set

from models.schemas import PIIType

# ---------------------------------------------------------------------------
# Legal-suffix regex — shared across all noise filters
# ---------------------------------------------------------------------------

LEGAL_SUFFIX_RE: _re.Pattern[str] = _re.compile(
    r'\b(?:inc|corp|ltd|llc|llp|plc|co|lp|sas|sarl|gmbh|ag|bv|nv|'
    r'kg|kgaa|ohg|ug|mbh|e\.?k\.?|e\.?v\.?|se|'
    r'lt[ée]e|limit[ée]e|enr|s\.?e\.?n\.?c\.?|'
    r's\.?a\.?r?\.?l?\.?|s\.?p\.?a\.?|s\.?r\.?l\.?)\b\.?',
    _re.IGNORECASE,
)


def has_legal_suffix(text: str) -> bool:
    """Return True if *text* contains a legal company suffix anywhere."""
    return bool(LEGAL_SUFFIX_RE.search(text.strip()))


# ---------------------------------------------------------------------------
# Language dictionaries — loaded once at import time
# ---------------------------------------------------------------------------

_DICT_DIR = Path(__file__).parent / "dictionaries"
_SUPPORTED_LANGS = ("en", "fr", "de", "es", "it", "nl", "pt")


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


_common_words: frozenset[str] = _load_dictionaries()
_german_words: frozenset[str] = _load_single_dict("de")


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
    clean = text.strip()
    low = clean.lower()
    if low in _common_words:
        return True
    _stripped = _ARTICLE_PREFIX_RE.sub("", clean)
    if _stripped and _stripped.lower() in _common_words:
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
        w.lower() in _common_words
        or all(c in "-\u2013\u2014/." for c in w)
        for w in words
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
    # German
    "gebäude", "gebaude", "gebaeude", "grundstück", "grundstueck",
    "anlage", "anlagen", "lager", "lagerhalle",
    "werkstatt", "werkstätte", "werkstaette",
    "fabrik", "büro", "buero",
    "halle", "hallen", "gelände", "gelaende",
    "ausstattung", "einrichtung", "möbel", "moebel",
    "schwimmbad", "turnhalle", "sportplatz",
    "abschreibung", "abschreibungen",
    "rückstellung", "rueckstellung", "rückstellungen", "rueckstellungen",
    "vermögen", "vermoegen", "inventar",
    "bilanz", "betrag", "ergebnis", "saldo",
    # Spanish
    "edificio", "edificios", "nave", "naves",
    "almacén", "almacen", "almacenes",
    "taller", "talleres", "fábrica", "fabrica",
    "oficina", "oficinas",
    "local", "locales", "recinto", "recintos",
    "instalación", "instalacion", "instalaciones",
    "terreno", "terrenos", "solar", "solares",
    "piscina", "gimnasio", "polideportivo",
    "mobiliario", "equipamiento",
    "amortización", "amortizacion",
    "provisión", "provision", "provisiones",
    "activo", "pasivo", "balance",
    # Italian
    "edificio", "edifici", "capannone", "capannoni",
    "magazzino", "magazzini", "officina", "officine",
    "stabilimento", "stabilimenti",
    "terreno", "terreni", "locale", "locali",
    "impianto", "impianti",
    "arredamento", "attrezzatura", "attrezzature",
    "ammortamento", "ammortamenti",
    "accantonamento", "accantonamenti",
    "attivo", "passivo", "bilancio",
    # Dutch
    "gebouw", "gebouwen", "terrein", "terreinen",
    "magazijn", "magazijnen", "werkplaats",
    "fabriek", "kantoor", "kantoren",
    "hal", "hallen", "pand", "panden",
    "ruimte", "ruimten",
    "zwembad", "sporthal",
    "meubilair", "apparatuur", "inventaris",
    "afschrijving", "afschrijvingen",
    "voorziening", "voorzieningen",
    "activa", "passiva", "balans",
    # Portuguese
    "edifício", "edificio", "edifícios", "edificios",
    "armazém", "armazem", "armazéns", "armazens",
    "oficina", "oficinas", "fábrica", "fabrica",
    "terreno", "terrenos",
    "instalação", "instalacao", "instalações", "instalacoes",
    "piscina", "ginásio", "ginasio",
    "mobiliário", "mobiliario", "equipamento", "equipamentos",
    "amortização", "amortizacao",
    "provisão", "provisao", "provisões", "provisoes",
    "ativo", "passivo", "balanço", "balanco",
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
    # German
    "bilanz", "einnahmen", "ausgaben", "einnahme", "ausgabe",
    "gehalt", "gehälter", "gehaelter", "lohn", "löhne", "loehne",
    "miete", "mieten", "pacht",
    "steuer", "steuern", "mehrwertsteuer",
    "dividende", "dividenden",
    "zins", "zinsen",
    "gewinn", "verlust", "ertrag", "erträge", "ertraege",
    "aufwand", "aufwendungen", "kosten",
    "abschreibung", "abschreibungen",
    "rückstellung", "rueckstellung", "rückstellungen", "rueckstellungen",
    "rücklage", "ruecklage", "rücklagen", "ruecklagen",
    "vermögen", "vermoegen", "kapital",
    "schuld", "schulden", "forderung", "forderungen",
    "umsatz", "umsätze", "umsaetze",
    "kasse", "konto", "konten",
    "betrag", "beträge", "betraege", "saldo",
    "ergebnis", "ergebnisse",
    "buchung", "buchungen",
    "inventar", "vorräte", "vorraete",
    "seite", "abschnitt", "kapitel", "anhang", "tabelle",
    "gesamt", "notiz", "anmerkung",
    # Spanish
    "balance", "ingreso", "ingresos", "gasto", "gastos",
    "salario", "salarios", "sueldo", "sueldos",
    "alquiler", "alquileres", "renta", "rentas",
    "impuesto", "impuestos",
    "dividendo", "dividendos",
    "interés", "interes", "intereses",
    "beneficio", "beneficios", "pérdida", "perdida", "pérdidas", "perdidas",
    "amortización", "amortizacion", "depreciación", "depreciacion",
    "provisión", "provision", "provisiones",
    "deuda", "deudas", "crédito", "credito",
    "capital", "patrimonio",
    "activo", "activos", "pasivo", "pasivos",
    "cuenta", "cuentas", "partida", "partidas",
    "resultado", "resultados", "ejercicio",
    "factura", "facturas", "fondo", "fondos",
    "caja", "tesorería", "tesoreria",
    "inventario", "existencias",
    "página", "pagina", "sección", "seccion", "capítulo", "capitulo",
    "anexo", "tabla", "total",
    # Italian
    "bilancio", "entrata", "entrate", "spesa", "spese",
    "stipendio", "stipendi", "salario", "salari",
    "affitto", "affitti", "locazione",
    "imposta", "imposte", "iva",
    "dividendo", "dividendi",
    "interesse", "interessi",
    "utile", "perdita", "perdite",
    "ammortamento", "ammortamenti",
    "accantonamento", "accantonamenti",
    "debito", "debiti", "credito", "crediti",
    "capitale", "patrimonio",
    "attivo", "passivo",
    "conto", "conti", "voce", "voci",
    "risultato", "risultati", "esercizio",
    "fattura", "fatture", "fondo", "fondi",
    "cassa", "tesoreria",
    "inventario",
    "pagina", "sezione", "capitolo", "allegato", "tabella",
    "totale", "nota", "note",
    # Dutch
    "balans", "inkomsten", "uitgaven", "inkomst", "uitgave",
    "salaris", "salarissen", "loon", "lonen",
    "huur", "huren", "pacht",
    "belasting", "belastingen", "btw",
    "dividend",
    "rente",
    "winst", "verlies",
    "afschrijving", "afschrijvingen",
    "voorziening", "voorzieningen",
    "schuld", "schulden", "vordering", "vorderingen",
    "vermogen", "kapitaal",
    "activa", "passiva",
    "rekening", "rekeningen",
    "resultaat", "resultaten", "boekjaar",
    "factuur", "facturen", "fonds", "fondsen",
    "kas",
    "inventaris", "voorraad", "voorraden",
    "pagina", "afdeling", "hoofdstuk", "bijlage", "tabel",
    "totaal", "opmerking", "noot",
    # Portuguese
    "balanço", "balanco", "receita", "receitas", "despesa", "despesas",
    "salário", "salario", "salários", "salarios",
    "aluguel", "aluguéis", "alugueis",
    "imposto", "impostos",
    "dividendo", "dividendos",
    "juro", "juros",
    "lucro", "lucros", "prejuízo", "prejuizo",
    "amortização", "amortizacao", "depreciação", "depreciacao",
    "provisão", "provisao", "provisões", "provisoes",
    "dívida", "divida", "dívidas", "dividas",
    "crédito", "credito", "créditos", "creditos",
    "capital", "patrimônio", "patrimonio",
    "ativo", "ativos", "passivo", "passivos",
    "conta", "contas",
    "resultado", "resultados", "exercício", "exercicio",
    "fatura", "faturas", "fundo", "fundos",
    "caixa", "tesouraria",
    "inventário", "inventario", "estoque", "estoques",
    "página", "pagina", "seção", "secao", "capítulo", "capitulo",
    "anexo", "tabela", "total",
}


# ── German compound-word decomposition ────────────────────────────────────
# German creates compound nouns by concatenation (Haupt+Mieter → Hauptmieter).
# wordfreq dictionaries miss most compounds.  If a single word can be split
# into two known dictionary parts (with optional Fugen-element s/es/n/en/er/e)
# it is almost certainly a common noun, not a person name.

_FUGENLAUTE = ("es", "en", "er", "ns", "s", "n", "e")  # longest-first


def _is_german_compound_noun(word: str) -> bool:
    """Return True if *word* is a German compound of 2+ dictionary parts.

    Works by trying every split of the (lowercased, optionally inflection-
    stripped) form and checking left ∈ dict and right ∈ dict (with optional
    Fugen-element between them).

    Uses the German-only dictionary to avoid cross-language false positives
    (e.g. "Martin" → "mar" (ES) + "tin" (EN)).
    """
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
        # French
        "hypothécaire", "hypothecaire", "hypothèque", "hypotheque",
        "remboursable", "remboursement", "remboursements",
        "mensuel", "mensuels", "mensuelle", "mensuelles",
        "trimestriel", "trimestriels", "trimestrielle", "trimestrielles",
        "annuel", "annuels", "annuelle", "annuelles",
        "échéance", "echeance", "échéances", "echeances",
        "capital", "intérêt", "interet", "intérêts", "interets",
        "emprunt", "emprunts", "prêt", "pret", "prêts", "prets",
        "créancier", "creancier", "débiteur", "debiteur",
        # English
        "mortgage", "mortgages",
        "repayment", "repayments", "repayable",
        "monthly", "quarterly", "annually",
        "maturity", "maturities",
        "principal", "interest", "interests",
        "loan", "loans", "lender", "borrower",
        "creditor", "debtor",
        # German
        "hypothek", "hypotheken", "hypothekarisch",
        "rückzahlung", "rueckzahlung", "tilgung", "tilgungen",
        "monatlich", "vierteljährlich", "vierteljaehrlich", "jährlich", "jaehrlich",
        "fälligkeit", "faelligkeit",
        "darlehen", "kredit", "kredite",
        "gläubiger", "glaeubiger", "schuldner",
        # Spanish
        "hipoteca", "hipotecas", "hipotecario", "hipotecaria",
        "reembolso", "reembolsos", "reembolsable",
        "mensual", "mensuales", "trimestral", "trimestrales",
        "anual", "anuales",
        "vencimiento", "vencimientos",
        "préstamo", "prestamo", "préstamos", "prestamos",
        "acreedor", "acreedores", "deudor", "deudores",
        # Italian
        "ipoteca", "ipoteche", "ipotecario", "ipotecaria",
        "rimborso", "rimborsi", "rimborsabile",
        "mensile", "mensili", "trimestrale", "trimestrali",
        "annuale", "annuali",
        "scadenza", "scadenze",
        "mutuo", "mutui", "prestito", "prestiti",
        "creditore", "creditori", "debitore", "debitori",
        # Dutch
        "hypotheek", "hypotheken",
        "terugbetaling", "terugbetalingen", "aflossing", "aflossingen",
        "maandelijks", "driemaandelijks", "kwartaal", "jaarlijks",
        "vervaldatum",
        "lening", "leningen",
        "schuldeiser", "schuldenaar",
        # Portuguese
        "hipoteca", "hipotecas", "hipotecário", "hipotecario",
        "reembolso", "reembolsos", "reembolsável", "reembolsavel",
        "mensal", "mensais", "trimestral", "trimestrais",
        "anual", "anuais",
        "vencimento", "vencimentos",
        "empréstimo", "emprestimo", "empréstimos", "emprestimos",
        "credor", "credores", "devedor", "devedores",
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


# ── Phone-label stripping for ADDRESS regions ────────────────────────────

# These labels (and their multilingual counterparts) indicate a phone/fax
# line.  They should never be part of a detected ADDRESS region.
_PHONE_LABEL_RE = _re.compile(
    r"(?:^|\n)\s*"
    r"(?:"
    r"Phone|Tel(?:ephone|efon|[ée]phone)?|T[ée]l(?:[ée]phone)?|"
    r"Mobile|Cell(?:ulare)?|Celular|Fax|"
    r"Portable|Fixe|Rufnummer|Handy|Mobil|"
    r"Tel[ée]fono"
    r")"
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
    # Strip phone label lines from end
    cleaned = _PHONE_LABEL_RE.sub("", text).strip()
    return cleaned if cleaned else text
