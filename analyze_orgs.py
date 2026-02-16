import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

d = json.load(open('debug-p2.json', encoding='utf-16'))
orgs = [r for r in d['regions'] if r['type'] == 'ORG']
print(f'Total ORGs on page 2: {len(orgs)}')
for r in orgs:
    text = r['text']
    print(f"{r['source']}: {text!r} (conf={r['confidence']})")
