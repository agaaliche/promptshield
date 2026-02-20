"""Bulk detection audit — Phase 2: inventory + collect regions."""

import requests
import json
import sys

BASE = "http://127.0.0.1:8910"
HEADERS = {"X-Requested-With": "XMLHttpRequest"}


def get_docs():
    r = requests.get(f"{BASE}/api/documents?paginated=false&limit=500", headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return data.get("items", [])
    return data


def get_doc_detail(doc_id):
    r = requests.get(f"{BASE}/api/documents/{doc_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def get_regions(doc_id):
    r = requests.get(f"{BASE}/api/documents/{doc_id}/regions", headers=HEADERS)
    r.raise_for_status()
    return r.json()


def trigger_detection(doc_id):
    r = requests.post(
        f"{BASE}/api/documents/{doc_id}/detect",
        headers=HEADERS,
        json={"layers": ["regex", "ner", "gliner"]},
    )
    r.raise_for_status()
    return r.json()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inventory"

    docs = get_docs()
    print(f"Total documents: {len(docs)}\n")

    if cmd == "inventory":
        for d in docs:
            print(f"  {d['doc_id']:>16s}  pages={d['page_count']:>3d}  {d['original_filename']}")

    elif cmd == "detect":
        # Trigger detection on all docs that have 0 regions
        for d in docs:
            regions = get_regions(d["doc_id"])
            if len(regions) == 0:
                print(f"  Detecting: {d['original_filename']} ({d['doc_id']})...")
                try:
                    result = trigger_detection(d["doc_id"])
                    print(f"    -> {result.get('region_count', '?')} regions")
                except Exception as e:
                    print(f"    -> ERROR: {e}")
            else:
                print(f"  Already has {len(regions)} regions: {d['original_filename']}")

    elif cmd == "collect":
        # Collect all regions, group by type, dump stats
        all_regions = []
        for d in docs:
            regions = get_regions(d["doc_id"])
            for r in regions:
                r["_doc_id"] = d["doc_id"]
                r["_filename"] = d["original_filename"]
            all_regions.extend(regions)

        print(f"Total regions across all docs: {len(all_regions)}\n")

        # Group by entity type
        by_type = {}
        for r in all_regions:
            t = r.get("pii_type", "UNKNOWN")
            by_type.setdefault(t, []).append(r)

        print("=== REGIONS BY TYPE ===")
        for t in sorted(by_type.keys()):
            items = by_type[t]
            print(f"\n  {t}: {len(items)} regions")
            # Show unique texts
            texts = {}
            for r in items:
                txt = r.get("text", "").strip()
                if txt:
                    texts.setdefault(txt, []).append(r["_filename"])
            # Sort by frequency
            for txt, fnames in sorted(texts.items(), key=lambda x: -len(x[1]))[:30]:
                count = len(fnames)
                unique_files = len(set(fnames))
                print(f"    [{count:>3d} hits, {unique_files:>2d} files] {txt[:100]}")

    elif cmd == "fps":
        # Dump likely false positives: short texts, common words, low confidence
        all_regions = []
        for d in docs:
            regions = get_regions(d["doc_id"])
            for r in regions:
                r["_doc_id"] = d["doc_id"]
                r["_filename"] = d["original_filename"]
            all_regions.extend(regions)

        print(f"Total regions: {len(all_regions)}\n")

        # Suspected FPs: very short text, single word, common patterns
        print("=== POTENTIAL FALSE POSITIVES ===\n")

        # 1. Single-word ORG
        print("--- Single-word ORG (often FP) ---")
        for r in all_regions:
            if r.get("pii_type") == "ORG":
                txt = r.get("text", "").strip()
                words = txt.split()
                if len(words) <= 1 and len(txt) < 20:
                    print(f"  [{r['_filename']:>40s}] p{r.get('page_number','?')} : {txt!r}")

        # 2. Very short PERSON names (1 word)
        print("\n--- Single-word PERSON (often FP) ---")
        for r in all_regions:
            if r.get("pii_type") == "PERSON":
                txt = r.get("text", "").strip()
                words = txt.split()
                if len(words) <= 1 and len(txt) < 15:
                    print(f"  [{r['_filename']:>40s}] p{r.get('page_number','?')} : {txt!r}")

        # 3. Regions with low confidence
        print("\n--- Low confidence (< 0.5) ---")
        for r in all_regions:
            conf = r.get("confidence", 1.0)
            if conf < 0.5:
                txt = r.get("text", "").strip()
                print(f"  [{r['_filename']:>40s}] p{r.get('page_number','?')} {r.get('pii_type','?'):>10s} conf={conf:.2f} : {txt!r}")

        # 4. Possible header/footer FPs (same text on many pages)
        print("\n--- Same text detected on 3+ pages (header/footer FP?) ---")
        text_pages = {}
        for r in all_regions:
            txt = r.get("text", "").strip()
            key = (r["_doc_id"], txt)
            text_pages.setdefault(key, set()).add(r.get("page_number", 0))
        for (doc_id, txt), pages in sorted(text_pages.items(), key=lambda x: -len(x[1])):
            if len(pages) >= 3:
                fname = next((r["_filename"] for r in all_regions if r["_doc_id"] == doc_id), doc_id)
                etype = next((r.get("pii_type", "?") for r in all_regions if r["_doc_id"] == doc_id and r.get("text", "").strip() == txt), "?")
                print(f"  [{fname:>40s}] {etype:>10s} on {len(pages)} pages: {txt!r}")

    elif cmd == "zero":
        # Find docs/pages with zero regions (possible missed detections)
        print("=== DOCS/PAGES WITH ZERO REGIONS ===\n")
        for d in docs:
            regions = get_regions(d["doc_id"])
            if len(regions) == 0:
                print(f"  NO REGIONS: {d['original_filename']} ({d['page_count']} pages)")
            else:
                # Check per-page
                pages_with_regions = set(r.get("page_number") for r in regions)
                missing = [p for p in range(1, d["page_count"] + 1) if p not in pages_with_regions]
                if missing:
                    print(f"  {d['original_filename']}: pages with 0 regions: {missing}")

    elif cmd == "dump":
        # Full JSON dump for offline analysis
        result = {}
        for d in docs:
            regions = get_regions(d["doc_id"])
            result[d["doc_id"]] = {
                "filename": d["original_filename"],
                "page_count": d["page_count"],
                "regions": regions,
            }
        with open("_audit_dump.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Dumped to _audit_dump.json ({len(result)} docs)")


if __name__ == "__main__":
    main()
