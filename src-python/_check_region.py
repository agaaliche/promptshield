import requests, json
HEADERS = {"X-Requested-With": "XMLHttpRequest"}
BASE = "http://127.0.0.1:8910"
r = requests.get(f"{BASE}/api/documents?paginated=false&limit=500", headers=HEADERS)
docs = r.json()
for d in docs:
    rr = requests.get(f"{BASE}/api/documents/{d['doc_id']}/regions", headers=HEADERS)
    regions = rr.json()
    if regions:
        print(json.dumps(regions[0], indent=2, default=str))
        print("---")
        print("Keys:", list(regions[0].keys()))
        break
