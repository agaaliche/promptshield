"""Test detect endpoint and count regions."""
import requests
import sys

BASE = "http://localhost:8910"

# Get docs
docs = requests.get(f"{BASE}/api/documents", params={"paginated": "false", "limit": 500}).json()
print(f"Total docs: {len(docs)}")

if len(sys.argv) > 1 and sys.argv[1] == "detect":
    # Re-detect all
    ok = 0
    err = 0
    for i, d in enumerate(docs):
        doc_id = d["doc_id"]
        fn = d.get("original_filename", "?")
        try:
            r = requests.post(
                f"{BASE}/api/documents/{doc_id}/detect",
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=300,
            )
            if r.status_code == 200:
                ok += 1
                rc = r.json().get("region_count", "?")
                if (i + 1) % 10 == 0:
                    print(f"  [{i+1}/{len(docs)}] {rc} regions - {fn}")
            else:
                err += 1
                if err <= 5:
                    print(f"  ERROR [{i+1}] {r.status_code}: {r.text[:100]} - {fn}")
        except Exception as e:
            err += 1
            if err <= 5:
                print(f"  EXCEPTION [{i+1}]: {e}")
    print(f"\nDetection: {ok} success, {err} errors")

# Count regions
total = 0
by_type = {}
for d in docs:
    doc_id = d["doc_id"]
    regions = requests.get(f"{BASE}/api/documents/{doc_id}/regions").json()
    total += len(regions)
    for r in regions:
        t = r.get("pii_type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

print(f"\nTotal regions: {total}")
print(f"Before fixes: 5,862")
print(f"Change: {total - 5862:+d} ({(total - 5862) / 5862 * 100:+.1f}%)")
print(f"\nBy type:")
for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
    print(f"  {t:20s}: {c:5d}")
