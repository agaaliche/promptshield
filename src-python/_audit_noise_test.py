"""Quick diagnostic: test noise filters against known FPs."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from core.detection.noise_filters import _is_org_pipeline_noise, _is_person_pipeline_noise, _is_loc_pipeline_noise

# Top ORG FPs from audit
org_fps = [
    "de l", "de\nl", "d'une", "le plus", "Déboursés", "repreneuriat",
    "Choix 2", "à l", "Equipements", "a payer", "invalidité résulte",
    "Annexe 1", "la fin de", "la TPS/TVH", "période d",
    "SEUIL DE RENTABILITÉ", "l'entreprise", "lentreprise",
    "de l'entreprise.", "Annexe 3", "Annexe 2", "le plus",
    "informations financières", "L'entreprise", "Perles écoconçues",
    "d'assurance", "OSEntreprendre", "L'Esprit du repreneuriat",
    "BÉNÉFICES NON RÉPARTIS PRÉVISIONNELS\nPOUR LES EXERCICES SE",
    "NOTES AFFÉRENTES AUX ÉTATS FINANCIERS\nPOUR LES EXERCICES SE TERMINANT",
    "POUR LES EXERCICES SE TERMINANT",
    "CRA\nSENC",
    "Agence 08032",
]

print("=== ORG NOISE FILTER TEST ===")
for t in org_fps:
    result = _is_org_pipeline_noise(t)
    status = "✓ FILTERED" if result else "✗ MISSED"
    print(f"  {status}: {t!r}")

# Top PERSON FPs from audit
person_fps = [
    "la personne", "la compagnie", "Prêteur", "Emprunteur", "emploi",
    "Signature", "travaux", "la société", "client", "période",
    "Additionnez", "Intérêts", "Incomplete", "www.paiements.ca",
    "kombucha", "Tambucha", "Administrateur", "le Prêteur",
    "l'Emprunteur", "La compagnie", "la\npersonne", "la\ncompagnie",
    "OSEntreprendre", "Émission", "intérêts", "rentemensuelle",
    "poudre de nacre", "Abri", "Processus", "inscrite", "livraison",
    "Docusign", "DocuSign", "Horodatage", "distribution", "Date",
    "Mon entreprise", "ADDITIONNELLE :", "signature",
    "L'entreprise et/ou le promoteur", "l'entreprise et/ou le promoteur",
    "L'entrepreneur flexipreneur", "le Producteur", "Le Producteur",
    "débiteur", "Services Voile Horizon",
]

print("\n=== PERSON NOISE FILTER TEST ===")
for t in person_fps:
    result = _is_person_pipeline_noise(t)
    status = "✓ FILTERED" if result else "✗ MISSED"
    print(f"  {status}: {t!r}")

# LOCATION FPs
loc_fps = [
    "PROTÉGÉ B", "Location", "location", "localement",
    "l'emplacement", "Pays", "Province / Territoire",
    "Responsable local ou régional", "régions",
    "Installation de mouillages", "outre-mer",
]

print("\n=== LOCATION NOISE FILTER TEST ===")
for t in loc_fps:
    result = _is_loc_pipeline_noise(t)
    status = "✓ FILTERED" if result else "✗ MISSED"
    print(f"  {status}: {t!r}")
