#!/usr/bin/env python3
"""Test Quebec-style company number pattern"""

import re

# The updated pattern for numbered companies
pattern = re.compile(
    r"\b\d{3,10}(?:-\d{3,10})?"  # 3-10 digits, optionally followed by dash and more digits
    r"\s+(?:[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\-']{1,20}\s+){0,3}"
    r"(?:Inc|Corp|LLC|Ltd|LLP|PLC|Co|LP"
    r"|GmbH|AG|KG|KGaA|OHG|e\.?K\.?|UG|mbH"
    r"|BV|B\.?V\.?|NV|N\.?V\.?"
    r"|S\.?A\.?R?\.?L?\.?|S\.?L\.?U?\.?|S\.?C\.?|S\.?R\.?L\.?"
    r"|S\.?p\.?A\.?|S\.?a\.?s\.?|S\.?n\.?c\.?"
    r"|Lt[ée]e|Limit[ée]e|Lda|Ltda|Enr\.?g?\.?"
    r"|A/S|ApS|AS|ASA|AB|Oy|Oyj)\b\.?",
    re.IGNORECASE
)

test_cases = [
    "9425-7524 Québec inc.",
    "9425-7524 Quebec inc.",
    "123456 Company Inc.",
    "1234-5678 Ontario Ltd.",
    "9425-7524 Québec Inc.",
    "société 9425-7524 Québec inc. et sa filiale",
]

print("Testing Quebec-style company number pattern:\n")
for test in test_cases:
    match = pattern.search(test)
    if match:
        print(f"✓ MATCH: '{test}' -> '{match.group()}'")
    else:
        print(f"✗ NO MATCH: '{test}'")
