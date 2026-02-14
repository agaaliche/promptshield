"""Bounding-box geometry utilities for PII region processing."""

from __future__ import annotations

from models.schemas import BBox, PIIRegion


def _bbox_overlap_area(a: BBox, b: BBox) -> float:
    """Return the area of intersection between two bounding boxes."""
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _bbox_area(b: BBox) -> float:
    """Return the area of a bounding box."""
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _resolve_bbox_overlaps(regions: list[PIIRegion]) -> list[PIIRegion]:
    """Ensure no two highlight rectangles overlap on the same page.

    Strategy:
    1. Sort regions by area descending (process larger boxes first).
    2. For each pair with overlapping bboxes, shrink or clip the
       lower-confidence region so it no longer overlaps.
    3. If clipping would reduce a region to near-zero area, drop it.
    """
    if len(regions) <= 1:
        return regions

    result = sorted(regions, key=lambda r: -r.confidence)
    final: list[PIIRegion] = []

    for region in result:
        bbox = BBox(
            x0=region.bbox.x0,
            y0=region.bbox.y0,
            x1=region.bbox.x1,
            y1=region.bbox.y1,
        )

        for keeper in final:
            if _bbox_overlap_area(bbox, keeper.bbox) <= 0:
                continue

            overlap_x = min(bbox.x1, keeper.bbox.x1) - max(bbox.x0, keeper.bbox.x0)
            overlap_y = min(bbox.y1, keeper.bbox.y1) - max(bbox.y0, keeper.bbox.y0)

            cx = (bbox.x0 + bbox.x1) / 2
            cy = (bbox.y0 + bbox.y1) / 2
            kcx = (keeper.bbox.x0 + keeper.bbox.x1) / 2
            kcy = (keeper.bbox.y0 + keeper.bbox.y1) / 2

            if overlap_y <= overlap_x:
                if cy < kcy:
                    bbox = BBox(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=keeper.bbox.y0)
                else:
                    bbox = BBox(x0=bbox.x0, y0=keeper.bbox.y1, x1=bbox.x1, y1=bbox.y1)
            else:
                if cx < kcx:
                    bbox = BBox(x0=bbox.x0, y0=bbox.y0, x1=keeper.bbox.x0, y1=bbox.y1)
                else:
                    bbox = BBox(x0=keeper.bbox.x1, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1)

        if bbox.width < 2 or bbox.height < 2:
            continue

        final.append(region.model_copy(update={"bbox": bbox}))

    return final
