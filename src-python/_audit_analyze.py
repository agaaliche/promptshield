"""Phase 3: Deep FP/FN analysis on the audit dump."""
import json
import sys
from collections import Counter

with open("_audit_dump.json", "r", encoding="utf-8") as f:
    data = json.load(f)

all_regions = []
for doc_id, doc in data.items():
    for r in doc["regions"]:
        r["_doc_id"] = doc_id
        r["_filename"] = doc["filename"]
    all_regions.extend(doc["regions"])

print(f"Total regions: {len(all_regions)}")
print(f"Total docs: {len(data)}")
print()

# === Type breakdown ===
type_counts = Counter(r["pii_type"] for r in all_regions)
print("=== TYPE BREAKDOWN ===")
for t, c in type_counts.most_common():
    print(f"  {t:>20s}: {c:>5d}")
print()

# === TOP FP CATEGORIES ===

# 1. ORG FALSE POSITIVES — Focus on most frequent ORG texts
print("=" * 80)
print("=== ORG FALSE POSITIVE ANALYSIS ===")
print("=" * 80)
org_texts = Counter()
org_examples = {}
for r in all_regions:
    if r["pii_type"] == "ORG":
        txt = r["text"].strip()
        org_texts[txt] += 1
        if txt not in org_examples:
            org_examples[txt] = r

print("\nTop 60 most frequent ORG detections:")
for txt, count in org_texts.most_common(60):
    ex = org_examples[txt]
    src = ex.get("source", "?")
    conf = ex.get("confidence", 0)
    print(f"  [{count:>4d}x] conf={conf:.2f} src={src:>8s} | {txt[:120]}")

# 2. PERSON FALSE POSITIVES
print()
print("=" * 80)
print("=== PERSON FALSE POSITIVE ANALYSIS ===")
print("=" * 80)
person_texts = Counter()
person_examples = {}
for r in all_regions:
    if r["pii_type"] == "PERSON":
        txt = r["text"].strip()
        person_texts[txt] += 1
        if txt not in person_examples:
            person_examples[txt] = r

print("\nTop 60 most frequent PERSON detections:")
for txt, count in person_texts.most_common(60):
    ex = person_examples[txt]
    src = ex.get("source", "?")
    conf = ex.get("confidence", 0)
    print(f"  [{count:>4d}x] conf={conf:.2f} src={src:>8s} | {txt[:120]}")

# 3. LOCATION FALSE POSITIVES
print()
print("=" * 80)
print("=== LOCATION FALSE POSITIVE ANALYSIS ===")
print("=" * 80)
loc_texts = Counter()
loc_examples = {}
for r in all_regions:
    if r["pii_type"] == "LOCATION":
        txt = r["text"].strip()
        loc_texts[txt] += 1
        if txt not in loc_examples:
            loc_examples[txt] = r

print("\nTop 30 most frequent LOCATION detections:")
for txt, count in loc_texts.most_common(30):
    ex = loc_examples[txt]
    src = ex.get("source", "?")
    conf = ex.get("confidence", 0)
    print(f"  [{count:>4d}x] conf={conf:.2f} src={src:>8s} | {txt[:120]}")

# 4. EMAIL FALSE POSITIVES (non-email-like texts)
print()
print("=" * 80)
print("=== EMAIL FALSE POSITIVE ANALYSIS ===")
print("=" * 80)
for r in all_regions:
    if r["pii_type"] == "EMAIL":
        txt = r["text"].strip()
        if "@" not in txt:
            print(f"  [{r['_filename']:>50s}] p{r['page_number']} conf={r.get('confidence',0):.2f} : {txt!r}")

# 5. PHONE FALSE POSITIVES (date-like patterns)
print()
print("=" * 80)
print("=== PHONE FALSE POSITIVE ANALYSIS ===")
print("=" * 80)
phone_texts = Counter()
for r in all_regions:
    if r["pii_type"] == "PHONE":
        txt = r["text"].strip()
        phone_texts[txt] += 1
print("All PHONE detections:")
for txt, count in phone_texts.most_common():
    print(f"  [{count:>4d}x] {txt!r}")

# 6. CREDIT_CARD - almost certainly all FPs
print()
print("=" * 80)
print("=== CREDIT_CARD DETECTIONS ===")
print("=" * 80)
for r in all_regions:
    if r["pii_type"] == "CREDIT_CARD":
        print(f"  [{r['_filename']:>50s}] p{r['page_number']} conf={r.get('confidence',0):.2f} : {r['text']!r}")

# 7. PASSPORT - almost certainly all FPs
print()
print("=" * 80)
print("=== PASSPORT DETECTIONS ===")
print("=" * 80)
for r in all_regions:
    if r["pii_type"] == "PASSPORT":
        print(f"  [{r['_filename']:>50s}] p{r['page_number']} conf={r.get('confidence',0):.2f} : {r['text']!r}")

# 8. DRIVER_LICENSE - check
print()
print("=" * 80)
print("=== DRIVER_LICENSE DETECTIONS ===")
print("=" * 80)
for r in all_regions:
    if r["pii_type"] == "DRIVER_LICENSE":
        print(f"  [{r['_filename']:>50s}] p{r['page_number']} conf={r.get('confidence',0):.2f} : {r['text']!r}")

# 9. SSN - check
print()
print("=" * 80)
print("=== SSN DETECTIONS ===")
print("=" * 80)
ssn_texts = Counter()
for r in all_regions:
    if r["pii_type"] == "SSN":
        txt = r["text"].strip()
        ssn_texts[txt] += 1
for txt, count in ssn_texts.most_common():
    print(f"  [{count:>4d}x] {txt!r}")

# 10. ADDRESS with "ET" pattern (suspicious)
print()
print("=" * 80)
print("=== SUSPICIOUS ADDRESS PATTERNS ===")
print("=" * 80)
addr_texts = Counter()
for r in all_regions:
    if r["pii_type"] == "ADDRESS":
        txt = r["text"].strip()
        addr_texts[txt] += 1
print("Top 20 ADDRESS detections:")
for txt, count in addr_texts.most_common(20):
    print(f"  [{count:>4d}x] {txt[:150]!r}")
