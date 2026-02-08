"""Debug GLiNER pipeline integration."""
import sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.DEBUG)

from core.detection.gliner_detector import detect_gliner
from core.detection.regex_detector import detect_regex

text = (
    "Les etats financiers ci-joints de 9169270 Canada inc. "
    "ont ete prepares par la direction de la societe. "
    "Jean-Pierre Tremblay, directeur financier, et Marie-Claire Dubois, "
    "presidente du conseil, ont approuve ces documents. "
    "Le siege social est situe au 1234 Boulevard Saint-Laurent, "
    "Montreal, Quebec H2X 2T1. "
    "Courriel: jpt@canadainc.ca  Tel: (514) 555-1234"
)

print("=== REGEX ===")
for m in detect_regex(text):
    print(f"  {m.pii_type.value:12s}  {m.confidence:.2f}  '{m.text}'")

print("\n=== GLINER ===")
gliner_matches = detect_gliner(text)
print(f"Found {len(gliner_matches)} matches:")
for m in gliner_matches:
    print(f"  {m.pii_type.value:12s}  {m.confidence:.2f}  pos={m.start}-{m.end}  '{m.text}'")
