"""Debug: trace ADDRESS detection on page 2."""
import json, logging
logging.basicConfig(level=logging.DEBUG)

from models.schemas import PageData
from core.detection.pipeline import detect_pii_on_page
from core.detection.regex_detector import detect_regex
from core.detection.merge import _merge_detections
from core.detection.ner_detector import detect_ner

doc = json.load(open(r"C:\Users\Amine\AppData\Local\doc-anonymizer\storage\documents\afdc3546da70.json"))
p = [p for p in doc["pages"] if p["page_number"] == 2][0]
page = PageData(**p)

# Step 1: regex matches
regex_matches = detect_regex(page.full_text, page.text_blocks)
print(f"\n=== REGEX matches ({len(regex_matches)}) ===")
for m in regex_matches:
    if m.pii_type.value in ("ADDRESS", "ORG", "PHONE"):
        print(f"  {m.pii_type.value:12s} text={m.text!r:60s} start={m.start} end={m.end}")

# Step 2: ner matches
ner_matches = detect_ner(page.full_text, language="fr")
print(f"\n=== NER matches ({len(ner_matches)}) ===")
for m in ner_matches:
    print(f"  {m.pii_type.value:12s} text={m.text!r:60s} start={m.start} end={m.end}")

# Step 3: full merge
regions = _merge_detections(regex_matches, ner_matches, [], page, [])
print(f"\n=== Merged regions ({len(regions)}) ===")
for r in regions:
    print(f"  {r.pii_type.value:12s} src={r.source.value:8s} text={r.text!r:60s} bbox=({r.bbox.x0:.1f},{r.bbox.y0:.1f},{r.bbox.x1:.1f},{r.bbox.y1:.1f})")
