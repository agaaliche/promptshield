"""Debug regex pattern matching."""
import re
from core.detection.regex_patterns import _STANDALONE_PATTERNS, PIIType

test_text = """Les entreprises de restauration B.N. ltée"""

print(f"Test text: '{test_text}'")
print(f"Length: {len(test_text)}")
print()

# Find the connecting-word ORG pattern (it's roughly pattern index 15-20 in the list)
for idx, (pattern_str, pii_type, conf, flags) in enumerate(_STANDALONE_PATTERNS):
    if pii_type == PIIType.ORG and "de|du|des" in pattern_str:
        print(f"Pattern #{idx} (ORG connecting-word pattern):")
        print(f"  Flags: {flags}")
        print(f"  Confidence: {conf}")
        print()
        
        pattern = re.compile(pattern_str, flags)
        matches = list(pattern.finditer(test_text))
        print(f"  Matches: {len(matches)}")
        for m in matches:
            print(f"    - '{m.group()}' @ {m.start()}-{m.end()}")
        
        if not matches:
            print("  NO MATCHES - trying to debug...")
            # Test parts of the pattern
            print("  Testing pattern components:")
            
            #  Test if first word matches
            first_word_pattern = r"\b[A-ZÀ-Ü][a-zA-Zà-üÀ-Ü.\-']{1,25}"
            if re.search(first_word_pattern, test_text):
                print(f"    ✓ First word pattern matches: {re.search(first_word_pattern, test_text).group()}")
            else:
                print(f"    ✗ First word pattern does NOT match")
            
            # Test if suffix matches
            suffix_pattern = r"(?i:Lt[ée]e|Limit[ée]e|Inc|Corp|LLC)"
            if re.search(suffix_pattern, test_text):
                print(f"    ✓ Suffix pattern matches: {re.search(suffix_pattern, test_text).group()}")
            else:
                print(f"    ✗ Suffix pattern does NOT match")
        
        break
