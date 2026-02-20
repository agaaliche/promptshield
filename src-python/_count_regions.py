"""Quick region count after re-detection."""
import requests

BASE = "http://localhost:8910"
docs = requests.get(f"{BASE}/api/documents?paginated=false&limit=500").json()
if isinstance(docs, dict):
    docs = docs.get("items", docs.get("documents", []))

total_regions = 0
by_type = {}
for d in docs:
    doc_id = d["doc_id"]
    regions = requests.get(f"{BASE}/api/documents/{doc_id}/regions").json()
    total_regions += len(regions)
    for r in regions:
        t = r.get("pii_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

print(f"Total docs: {len(docs)}, Total regions: {total_regions}")
print(f"\nBefore: 5,862 regions")
print(f"After:  {total_regions} regions")
print(f"Reduction: {5862 - total_regions} ({(5862 - total_regions)/5862*100:.1f}%)")
print(f"\nBy type:")
for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
    print(f"  {t:20s}: {c:5d}")
