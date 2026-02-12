#!/usr/bin/env python3
"""Test full detection on Quebec company name"""

import sys
sys.path.insert(0, '.')

from core.detection.regex_detector import detect_regex

text = """
Le 1er octobre 2021, la société 9425-7524 Québec inc. et sa filiale, Les entreprises de restauration 
B.N. ltée, ont fusionné. La société issue de la fusion a conservé le nom de Les entreprises de 
restauration B.N. ltée.
"""

print("Testing full regex detection on Quebec company names:\n")
print(f"Text:\n{text}\n")

matches = detect_regex(text)
print(f"Found {len(matches)} matches:\n")
for match in matches:
    print(f"  [{match.pii_type.value}] '{match.text}' @ {match.start}-{match.end} (conf: {match.confidence:.2f})")
