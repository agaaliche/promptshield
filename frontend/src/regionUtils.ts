/**
 * Region overlap resolution and minimum-size enforcement utilities.
 */

import type { BBox, PIIRegion } from "./types";

/** Minimum region size in page coordinate units */
export const MIN_REGION_PAGE_UNITS = 5;

/**
 * Check whether two bboxes overlap.
 */
function overlaps(a: BBox, b: BBox): boolean {
  return a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
}

/**
 * Resolve all overlapping regions in one pass.
 *
 * Regions earlier in the array have priority (kept in place); later ones
 * get pushed along the axis with the smallest overlap.
 * Also enforces a minimum bbox size.
 */
export function resolveAllOverlaps(inputRegions: PIIRegion[]): PIIRegion[] {
  const result = inputRegions.map((r) => ({ ...r, bbox: { ...r.bbox } }));

  // Enforce minimum bbox size
  for (const r of result) {
    if (r.bbox.x1 - r.bbox.x0 < MIN_REGION_PAGE_UNITS) r.bbox.x1 = r.bbox.x0 + MIN_REGION_PAGE_UNITS;
    if (r.bbox.y1 - r.bbox.y0 < MIN_REGION_PAGE_UNITS) r.bbox.y1 = r.bbox.y0 + MIN_REGION_PAGE_UNITS;
  }

  // Group by page
  const byPage = new Map<number, number[]>();
  result.forEach((r, idx) => {
    if (r.action === "CANCEL") return;
    const arr = byPage.get(r.page_number) || [];
    arr.push(idx);
    byPage.set(r.page_number, arr);
  });

  for (const indices of byPage.values()) {
    for (let i = 1; i < indices.length; i++) {
      const box = result[indices[i]].bbox;
      for (let j = 0; j < i; j++) {
        const ob = result[indices[j]].bbox;
        if (!overlaps(box, ob)) continue;

        const overlapX = Math.min(box.x1, ob.x1) - Math.max(box.x0, ob.x0);
        const overlapY = Math.min(box.y1, ob.y1) - Math.max(box.y0, ob.y0);
        const cx = (box.x0 + box.x1) / 2;
        const cy = (box.y0 + box.y1) / 2;
        const ocx = (ob.x0 + ob.x1) / 2;
        const ocy = (ob.y0 + ob.y1) / 2;

        if (overlapY <= overlapX) {
          const shift = cy < ocy ? -overlapY : overlapY;
          box.y0 += shift;
          box.y1 += shift;
        } else {
          const shift = cx < ocx ? -overlapX : overlapX;
          box.x0 += shift;
          box.x1 += shift;
        }
      }
    }
  }
  return result;
}
