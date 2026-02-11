import json, os

f = os.path.join(os.environ['LOCALAPPDATA'], 'doc-anonymizer', 'storage', 'documents', 'f5c6660fc62e.json')
d = json.loads(open(f, encoding='utf-8').read())

p2 = [r for r in d['regions'] if r['page_number'] == 2]
print(f"Page 2 has {len(p2)} regions:")
for r in p2:
    b = r['bbox']
    t = r['text'][:40]
    act = r.get('action', '?')
    pii = r['pii_type']
    conf = r['confidence']
    src = r['source']
    print(f"  {t:42s} {pii:10s} conf={conf:.2f} {src:8s} action={act} bbox=({b['x0']:.1f},{b['y0']:.1f})->({b['x1']:.1f},{b['y1']:.1f})")
