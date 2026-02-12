"""Test full detection on sample French financial text."""
from core.detection import regex_detector, ner_detector

# Sample text from the PDF
test_text = """Le 1er octobre 2021, la société 9425-7524 Québec inc. et sa filiale, Les entreprises de restauration B.N. ltée, ont fusionné. La société issue de la fusion a conservé le nom de Les entreprises de restauration B.N. ltée.

Principales méthodes comptables

La méthode de comptabilité appliquée dans l'établissement des informations financières se fait au coût historique. Les immobilisations corporelles sont comptabilisées au coût. Elles sont amorties."""

print("=" * 70)
print("REGEX DETECTOR:")
print("=" * 70)
regex_matches = regex_detector.detect_regex(test_text)
for m in regex_matches:
    print(f"  [{m.pii_type.value:12s}] '{m.text}' @ {m.start}-{m.end} (conf: {m.confidence:.2f})")

print(f"\nTotal regex matches: {len(regex_matches)}")
print(f"ORG matches from regex: {len([m for m in regex_matches if m.pii_type.value == 'ORG'])}")

# Check if French NER is available
if ner_detector.is_french_ner_available():
    print("\n" + "=" * 70)
    print("NER DETECTOR (French):")
    print("=" * 70)
    ner_matches = ner_detector.detect_ner(test_text)
    for m in ner_matches:
        print(f"  [{m.pii_type.value:12s}] '{m.text}' @ {m.start}-{m.end} (conf: {m.confidence:.4f})")
    
    print(f"\nTotal NER matches: {len(ner_matches)}")
    print(f"ORG matches from NER: {len([m for m in ner_matches if m.pii_type.value == 'ORG'])}")
else:
    print("\nFrench NER not available")
