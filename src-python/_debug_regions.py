import json

doc = json.load(open(r"C:\Users\Amine\AppData\Local\doc-anonymizer\storage\documents\afdc3546da70.json"))
for r in doc.get("regions", []):
    if r["page_number"] == 2:
        bb = r["bbox"]
        print(f"id={r['id']} type={r['pii_type']:12s} src={r.get('source','?'):8s} text={r['text']!r:60s} bbox=({bb['x0']:.1f},{bb['y0']:.1f},{bb['x1']:.1f},{bb['y1']:.1f})")
