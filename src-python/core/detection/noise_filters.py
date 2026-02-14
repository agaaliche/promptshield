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
    "bilancio", "esercizio", "attivo", "passivo",
    "patrimonio", "ricavi", "ricavo", "costi", "costo",
    "utile", "perdita", "perdite",
    "ammortamento", "ammortamenti",
    "accantonamento", "accantonamenti",
    "debiti", "debito", "crediti", "credito",
    "fattura", "fatture", "fondi", "fondo",
    "cassa", "tesoreria", "capitale",
    "proventi", "provento", "oneri", "onere",
    "ratei", "risconti", "rateo", "risconto",
    "immobilizzazioni", "immobilizzazione",
    "partecipazioni", "partecipazione",
    "disponibilità", "disponibilita",
    "imposte", "imposta", "iva",
    "riserve", "riserva", "risultato", "risultati",
    "voce", "voci", "nota", "note",
    "conto", "conti", "economico", "finanziario",
    "rendiconto", "prospetto",
    "corporale", "corporali", "incorporale", "incorporali",
    "materiale", "materiali", "immateriale", "immateriali",
    # German
    "gesellschaft", "unternehmen", "abteilung",
    "firma", "konzern", "betrieb", "betriebe",
    "vorstand", "aufsichtsrat", "geschäftsführung", "geschaeftsfuehrung",
    "bilanz", "gewinn", "verlust", "ertrag", "erträge", "ertraege",
    "aufwand", "aufwendungen", "kosten",
    "umsatz", "umsätze", "umsaetze", "umsatzerlöse", "umsatzerloese",
    "vermögen", "vermoegen", "verbindlichkeiten", "verbindlichkeit",
    "eigenkapital", "fremdkapital",
    "rückstellung", "rueckstellung", "rückstellungen", "rueckstellungen",
    "abschreibung", "abschreibungen",
    "anlage", "anlagen", "anlagevermögen", "anlagevermoegen",
    "umlaufvermögen", "umlaufvermoegen",
    "forderungen", "forderung",
    "schulden", "schuld",
    "rücklage", "ruecklage", "rücklagen", "ruecklagen",
    "steuer", "steuern", "mehrwertsteuer",
    "kapital", "kapitalgesellschaft",
    "beteiligung", "beteiligungen",
    "jahresabschluss", "geschäftsjahr", "geschaeftsjahr",
    "bericht", "berichte", "lagebericht",
    "vertrag", "verträge", "vertraege",
    "gesetz", "verordnung", "satzung", "beschluss",
    "anhang", "anlage", "tabelle", "abbildung",
    "paragraph", "absatz", "bestimmung",
    "ergebnis", "ergebnisse", "saldo", "betrag", "beträge", "betraege",
    "zins", "zinsen", "dividende", "dividenden",
    "inventar", "vorräte", "vorraete",
    "kasse", "bank", "konto", "konten",
    "buchung", "buchungen", "buchführung", "buchfuehrung",
    "prüfung", "pruefung", "revision", "wirtschaftsprüfer", "wirtschaftspruefer",
    "feststellung", "feststellungen",
    "grundstück", "grundstueck", "grundstücke", "grundstuecke",
    "gebäude", "gebaeude", "ausstattung",
    "allgemein", "besonders", "ergänzend", "ergaenzend",
    # Spanish
    "empresa", "compañía", "compania", "división",
    "sociedad", "corporación", "corporacion",
    "departamento", "sección", "seccion", "junta", "comisión", "comision",
    "balance", "activo", "activos", "pasivo", "pasivos",
    "patrimonio", "ingresos", "ingreso", "gastos", "gasto",
    "beneficio", "beneficios", "pérdida", "perdida", "pérdidas", "perdidas",
    "amortización", "amortizacion", "depreciación", "depreciacion",
    "provisión", "provision", "provisiones",
    "deuda", "deudas", "crédito", "credito", "créditos", "creditos",
    "factura", "facturas", "fondos", "fondo",
    "caja", "tesorería", "tesoreria",
    "impuesto", "impuestos", "iva",
    "reserva", "reservas", "resultado", "resultados",
    "cuenta", "cuentas", "partida", "partidas",
    "ejercicio", "cierre", "consolidado", "consolidados",
    "informe", "informes", "memoria", "memorias",
    "ley", "decreto", "reglamento", "estatuto", "estatutos",
    "contrato", "contratos", "acuerdo", "acuerdos",
    "artículo", "articulo", "cláusula", "clausula", "anexo", "anexos",
    "tabla", "gráfico", "grafico", "cuadro",
    "capital", "acción", "accion", "acciones",
    "inversión", "inversion", "inversiones",
    "préstamo", "prestamo", "préstamos", "prestamos",
    "interés", "interes", "intereses",
    "dividendo", "dividendos",
    "inventario", "existencias",
    "auditoría", "auditoria", "auditor", "auditores",
    "verificación", "verificacion", "certificación", "certificacion",
    "observaciones", "recomendaciones", "conclusiones",
    # Dutch
    "vennootschap", "bedrijf", "onderneming", "maatschappij",
    "afdeling", "bestuur", "raad", "commissie",
    "balans", "activa", "passiva",
    "eigen", "vermogen", "vreemd",
    "omzet", "opbrengsten", "opbrengst",
    "kosten", "lasten", "baten",
    "winst", "verlies",
    "afschrijving", "afschrijvingen",
    "voorziening", "voorzieningen",
    "schuld", "schulden", "vordering", "vorderingen",
    "factuur", "facturen",
    "kas", "bank", "rekening", "rekeningen",
    "belasting", "belastingen", "btw",
    "reserve", "reserves", "resultaat", "resultaten",
    "jaarrekening", "boekjaar",
    "verslag", "rapport", "rapportage",
    "wet", "verordening", "statuut", "statuten",
    "overeenkomst", "contract", "contracten",
    "artikel", "clausule", "bijlage", "bijlagen",
    "tabel", "grafiek", "overzicht",
    "kapitaal", "aandeel", "aandelen",
    "investering", "investeringen",
    "lening", "leningen",
    "rente", "dividend",
    "voorraad", "voorraden",
    "accountant", "controle", "certificering",
    "toelichting", "opmerkingen", "aanbevelingen", "conclusie",
    # Portuguese
    "empresa", "companhia", "sociedade", "corporação", "corporacao",
    "departamento", "seção", "secao", "diretoria", "comissão", "comissao",
    "balanço", "balanco", "ativo", "ativos", "passivo", "passivos",
    "patrimônio", "patrimonio", "receita", "receitas",
    "despesa", "despesas", "custo", "custos",
    "lucro", "lucros", "prejuízo", "prejuizo", "prejuízos", "prejuizos",
    "amortização", "amortizacao", "depreciação", "depreciacao",
    "provisão", "provisao", "provisões", "provisoes",
    "dívida", "divida", "dívidas", "dividas",
    "crédito", "credito", "créditos", "creditos",
    "fatura", "faturas", "fundo", "fundos",
    "caixa", "tesouraria",
    "imposto", "impostos",
    "reserva", "reservas", "resultado", "resultados",
    "conta", "contas",
    "exercício", "exercicio",
    "relatório", "relatorio", "relatórios", "relatorios",
    "lei", "decreto", "regulamento", "estatuto", "estatutos",
    "contrato", "contratos", "acordo", "acordos",
    "artigo", "cláusula", "clausula", "anexo", "anexos",
    "tabela", "gráfico", "grafico", "quadro",
    "capital", "ação", "acao", "ações", "acoes",
    "investimento", "investimentos",
    "empréstimo", "emprestimo", "empréstimos", "emprestimos",
    "juro", "juros", "dividendo", "dividendos",
    "inventário", "inventario", "estoque", "estoques",
    "auditoria", "auditor", "auditores",
    "verificação", "verificacao", "certificação", "certificacao",
    "observações", "observacoes", "recomendações", "recomendacoes",
}


def _is_org_pipeline_noise(text: str) -> bool:
    """Return True if *text* looks like a noisy ORG false-positive."""
    clean = text.strip()
    low = clean.lower()
    if low in _ORG_PIPELINE_NOISE:
        return True
    _stripped = _re.sub(
        r"^(?:[LlDd]['\u2019]\s*"  # FR: l', d'
        r"|[Ll][eao]s?\s+|[Dd][eiu]s?\s+|[Uu]n[ea]?\s+"  # FR
        r"|[Ee]l\s+|[Ll]os\s+|[Ll]as\s+"  # ES
        r"|[Ii]l\s+|[Gg]li\s+|[Uu]n[oa]?\s+"  # IT
        r"|[Dd](?:er|ie|as|en|em|es)\s+|[Ee]in[e]?\s+"  # DE
        r"|[Hh]et\s+|[Dd]e\s+|[Ee]en\s+"  # NL
        r"|[Oo]s?\s+|[Aa]s?\s+"  # PT
        r")", "", clean)
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
        return True
    if len(words) >= 3:
        low_words = [w.lower() for w in words]
        if any(w in low_words for w in (
            "catégorie", "categorie", "category", "kategorie",
            "categoría", "categoria",
        )):
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
