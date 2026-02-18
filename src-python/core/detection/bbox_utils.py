"""Bounding-box geometry utilities for PII region processing.

Performance note (M4): ``_resolve_bbox_overlaps`` uses a grid-based
spatial index to reduce overlap checks from O(n²) to ~O(n) amortised.
"""

from __future__ import annotations

from collections import defaultdict

from models.schemas import BBox, PIIRegion
from core.detection.detection_config import BBOX_GRID_CELL_SIZE


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


# ---------------------------------------------------------------------------
# Grid-based spatial index for fast overlap queries
# ---------------------------------------------------------------------------

_GRID_CELL = BBOX_GRID_CELL_SIZE  # cell size in PDF points (~0.7 inch)


def _bbox_cells(bbox: BBox) -> set[tuple[int, int]]:
    """Return the set of grid cells that a bbox spans."""
    c0 = int(bbox.x0 // _GRID_CELL)
    r0 = int(bbox.y0 // _GRID_CELL)
    c1 = int(bbox.x1 // _GRID_CELL)
    r1 = int(bbox.y1 // _GRID_CELL)
    cells: set[tuple[int, int]] = set()
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            cells.add((r, c))
    return cells


def _resolve_bbox_overlaps(regions: list[PIIRegion]) -> list[PIIRegion]:
    """Ensure no two highlight rectangles overlap on the same page.

    Uses a grid-based spatial index so each region is only compared
    against nearby regions, reducing average complexity from O(n²) to
    ~O(n × k) where k is the average number of neighbours in the same
    grid cell (typically small).

    Strategy:
    1. Sort regions by confidence descending (process higher-conf first).
    2. For each region, check overlap only against accepted regions in
       the same grid cells; shrink/clip lower-confidence region.
    3. If clipping would reduce a region to near-zero area, drop it.
    """
    if len(regions) <= 1:
        return regions

    result = sorted(regions, key=lambda r: -r.confidence)
    final: list[PIIRegion] = []
    # Grid: cell → list of indices into `final`
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)

    for region in result:
        bbox = BBox(
            x0=region.bbox.x0,
            y0=region.bbox.y0,
            x1=region.bbox.x1,
            y1=region.bbox.y1,
        )

        # Collect candidate keepers from overlapping grid cells
        cells = _bbox_cells(bbox)
        seen_keepers: set[int] = set()
        for cell in cells:
            for ki in grid.get(cell, ()):
                seen_keepers.add(ki)

        for ki in seen_keepers:
            keeper = final[ki]
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

        idx = len(final)
        final.append(region.model_copy(update={"bbox": bbox}))
        # Register this region in all its grid cells
        for cell in _bbox_cells(bbox):
            grid[cell].append(idx)

    return final
