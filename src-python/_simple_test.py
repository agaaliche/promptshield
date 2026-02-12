import re

test_text = "Les entreprises de restauration B.N. ltée"

# The connecting-word pattern (simplified for testing)
pattern = (
    r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # First word
    r"(?:"  # Repeat 1-5 times:
    r"\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # Capitalized word
    r"|\s+(?:de|du|des|la|le|les|l'|d'|et|en)"  # OR connecting word
    r"\s+[a-zA-ZÀ-üÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"  # Followed by any word
    r"){1,5}"
    r"\s+(?i:Lt[ée]e|Limit[ée]e|Inc|Corp|LLC|Ltd)"  # Suffix (case-insensitive)
    r"\b\.?"
)

regex = re.compile(pattern)
matches = list(regex.finditer(test_text))

print(f"Test: '{test_text}'")
print(f"Pattern: {pattern[:100]}...")
print(f"Matches: {len(matches)}")
for m in matches:
    print(f"  - '{m.group()}' @ {m.start()}-{m.end()}")

if not matches:
    print("\nDEBUGGING:")
    # Test parts
    print("1. First word '[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\\-']{1,25}':")
    m1 = re.search(r"[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}", test_text)
    if m1:
        print(f"   ✓ Matches: '{m1.group()}'")
    else:
        print("   ✗ No match")
    
    print("\n2. Suffix '(?i:Lt[ée]e)':")
    m2 = re.search(r"(?i:Lt[ée]e)", test_text)
    if m2:
        print(f"   ✓ Matches: '{m2.group()}'")
    else:
        print("   ✗ No match")
    
    print("\n3. Full pattern without suffix:")
    pattern_no_suffix = (
        r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"
        r"(?:\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"
        r"|\s+(?:de|du|des|la|le|les|l'|d'|et|en)\s+[a-zA-ZÀ-üÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}){1,5}"
    )
    m3 = re.search(pattern_no_suffix, test_text)
    if m3:
        print(f"   ✓ Matches: '{m3.group()}'")
    else:
        print("   ✗ No match")

print("\n4. Testing with explicit text:")
explicit_tests = [
    ("Les", r"[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"),
    ("Les entreprises", r"[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}\s+[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"),
    ("ltée", r"(?i:Lt[ée]e)"),
    ("B.N. ltée", r"[A-Z.]+\s+(?i:lt[ée]e)"),
]
for text, pat in explicit_tests:
    if re.search(pat, text):
        print(f"   ✓ '{text}' matches '{pat}'")
    else:
        print(f"   ✗ '{text}' does NOT match '{pat}'")
