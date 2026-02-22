import json

doc = json.load(open(r"C:\Users\Amine\AppData\Local\doc-anonymizer\storage\documents\afdc3546da70.json"))
print("filename:", doc.get("filename", "?"))

for p in doc["pages"]:
    if "actionnaires" not in p.get("full_text", ""):
        continue
    pn = p["page_number"]
    print(f"\nPage {pn}: width={p['width']}, height={p['height']}")
    print(f"Text preview: {p.get('full_text','')[:400]}")
    print(f"\nAll text blocks ({len(p.get('text_blocks',[]))}):")
    for b in p.get("text_blocks", []):
        bb = b["bbox"]
        cx = (bb["x0"] + bb["x1"]) / 2
        cy = (bb["y0"] + bb["y1"]) / 2
        print(f"  text={b['text']!r:45s} x0={bb['x0']:7.1f} y0={bb['y0']:7.1f} x1={bb['x1']:7.1f} y1={bb['y1']:7.1f}  cx={cx:7.1f} cy={cy:7.1f}")

    # Show regions on this page
    print(f"\nRegions on page {pn}:")
    for r in doc.get("regions", []):
        if r["page_number"] == pn:
            bb = r["bbox"]
            print(f"  id={r['id']} type={r['pii_type']} text={r['text']!r} bbox=({bb['x0']:.1f},{bb['y0']:.1f},{bb['x1']:.1f},{bb['y1']:.1f}) src={r.get('source','?')}")
    break
