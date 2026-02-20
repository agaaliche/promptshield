import { describe, it, expect } from "vitest";
import { resolveAllOverlaps, MIN_REGION_PAGE_UNITS } from "../regionUtils";
import type { PIIRegion } from "../types";

function makeRegion(overrides: Partial<PIIRegion> = {}): PIIRegion {
  return {
    id: "r1",
    page_number: 1,
    bbox: { x0: 0, y0: 0, x1: 100, y1: 20 },
    text: "test",
    pii_type: "PERSON",
    confidence: 0.95,
    source: "NER",
    char_start: 0,
    char_end: 4,
    action: "PENDING",
    ...overrides,
  } as PIIRegion;
}

describe("resolveAllOverlaps", () => {
  it("should return empty array for empty input", () => {
    expect(resolveAllOverlaps([])).toEqual([]);
  });

  it("should enforce minimum region size", () => {
    const tiny = makeRegion({ bbox: { x0: 10, y0: 10, x1: 11, y1: 11 } });
    const result = resolveAllOverlaps([tiny]);
    const b = result[0].bbox;
    expect(b.x1 - b.x0).toBeGreaterThanOrEqual(MIN_REGION_PAGE_UNITS);
    expect(b.y1 - b.y0).toBeGreaterThanOrEqual(MIN_REGION_PAGE_UNITS);
  });

  it("should not modify non-overlapping regions", () => {
    const r1 = makeRegion({ id: "r1", bbox: { x0: 0, y0: 0, x1: 50, y1: 20 } });
    const r2 = makeRegion({ id: "r2", bbox: { x0: 100, y0: 0, x1: 150, y1: 20 } });
    const result = resolveAllOverlaps([r1, r2]);
    expect(result[0].bbox.x0).toBe(0);
    expect(result[1].bbox.x0).toBe(100);
  });

  it("should resolve overlapping regions by shifting", () => {
    const r1 = makeRegion({ id: "r1", bbox: { x0: 0, y0: 0, x1: 60, y1: 20 } });
    const r2 = makeRegion({ id: "r2", bbox: { x0: 30, y0: 0, x1: 90, y1: 20 } });
    const result = resolveAllOverlaps([r1, r2]);
    // r1 should stay in place, r2 should be shifted
    expect(result[0].bbox.x0).toBe(0);
    // r2 should no longer overlap with r1
    const a = result[0].bbox;
    const b = result[1].bbox;
    const overlaps = a.x0 < b.x1 && a.x1 > b.x0 && a.y0 < b.y1 && a.y1 > b.y0;
    expect(overlaps).toBe(false);
  });

  it("should skip CANCEL regions for overlap resolution", () => {
    const r1 = makeRegion({ id: "r1", bbox: { x0: 0, y0: 0, x1: 60, y1: 20 } });
    const r2 = makeRegion({ id: "r2", bbox: { x0: 30, y0: 0, x1: 90, y1: 20 }, action: "CANCEL" });
    const result = resolveAllOverlaps([r1, r2]);
    // r2 is CANCEL so overlap is ignored — position unchanged
    expect(result[1].bbox.x0).toBe(30);
  });

  it("should not mutate input array", () => {
    const r1 = makeRegion({ bbox: { x0: 0, y0: 0, x1: 60, y1: 20 } });
    const original = { ...r1.bbox };
    resolveAllOverlaps([r1]);
    expect(r1.bbox).toEqual(original);
  });
});
