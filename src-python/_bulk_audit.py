"""
Bulk detection audit script.
Phase 1: Inventory all documents and their current detection state.
"""
import requests
import json

BASE = "http://127.0.0.1:8910"
HEADERS = {"X-Requested-With": "XMLHttpRequest"}

# List all documents
r = requests.get(f"{BASE}/api/documents", headers=HEADERS)
docs = r.json()

print(f"Total documents: {len(docs)}")
print(f"{'idx':>3}  {'doc_id':<14} {'pages':>5} {'regions':>7} {'filename'}")
print("-" * 90)

for i, doc in enumerate(docs):
    doc_id = doc["id"]
    filename = doc.get("original_filename", "?")
    pages = len(doc.get("pages", []))
    
    # Get regions count
    rr = requests.get(f"{BASE}/api/documents/{doc_id}/regions", headers=HEADERS)
    regions = rr.json() if rr.status_code == 200 else []
    
    # Count by type
    type_counts = {}
    for reg in regions:
        t = reg["pii_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    
    type_str = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))
    
    print(f"{i+1:>3}  {doc_id:<14} {pages:>5} {len(regions):>7}  {filename}  [{type_str}]")
