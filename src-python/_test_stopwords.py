from core.detection.ner_detector import _is_false_positive_org_fr, _FR_ORG_STOPWORDS

test_words = ['Principales', 'principales', 'comptables', 'corporelles', 'Elles', 'société', 'activités']

print("Testing false positive filter:")
for w in test_words:
    result = _is_false_positive_org_fr(w)
    in_set = w.lower() in _FR_ORG_STOPWORDS
    print(f"  {w:20s} -> fp_filter={str(result):5s} in_stopwords={in_set}")

print(f"\nTotal FR_ORG_STOPWORDS: {len(_FR_ORG_STOPWORDS)}")
print("\nStopwords containing 'principales':")
for word in sorted(_FR_ORG_STOPWORDS):
    if 'principal' in word or 'comptable' in word or 'corporelle' in word:
        print(f"  - {word}")
