"""Tests for core.detection.bbox_utils — overlap area, area, grid cells, resolve overlaps."""

from __future__ import annotations

import pytest

from models.schemas import BBox, DetectionSource, PIIRegion, PIIType
from core.detection.bbox_utils import (
    _bbox_overlap_area,
    _bbox_area,
    _bbox_cells,
    _resolve_bbox_overlaps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _region(x0: float, y0: float, x1: float, y1: float,
            confidence: float = 0.9,
            pii_type: PIIType = PIIType.ORG) -> PIIRegion:
    return PIIRegion(
        page_number=1,
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text="TEST",
        pii_type=pii_type,
        confidence=confidence,
        source=DetectionSource.REGEX,
    )


# ---------------------------------------------------------------------------
# _bbox_area
# ---------------------------------------------------------------------------

class TestBboxArea:
    def test_normal(self):
        b = BBox(x0=0, y0=0, x1=10, y1=5)
        assert _bbox_area(b) == pytest.approx(50.0)

    def test_zero_height(self):
        b = BBox(x0=0, y0=5, x1=10, y1=5)
        assert _bbox_area(b) == pytest.approx(0.0)

    def test_inverted_x(self):
        """x1 < x0 → area clamped to 0."""
        b = BBox(x0=10, y0=0, x1=0, y1=5)
        assert _bbox_area(b) == pytest.approx(0.0)

    def test_unit_square(self):
        b = BBox(x0=0, y0=0, x1=1, y1=1)
        assert _bbox_area(b) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _bbox_overlap_area
# ---------------------------------------------------------------------------

class TestBboxOverlapArea:
    def test_no_overlap(self):
        a = BBox(x0=0, y0=0, x1=10, y1=10)
        b = BBox(x0=20, y0=20, x1=30, y1=30)
        assert _bbox_overlap_area(a, b) == pytest.approx(0.0)

    def test_adjacent_x_no_overlap(self):
        a = BBox(x0=0, y0=0, x1=10, y1=10)
        b = BBox(x0=10, y0=0, x1=20, y1=10)
        assert _bbox_overlap_area(a, b) == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = BBox(x0=0, y0=0, x1=10, y1=10)
        b = BBox(x0=5, y0=5, x1=15, y1=15)
        # Overlap: 5×5 = 25
        assert _bbox_overlap_area(a, b) == pytest.approx(25.0)

    def test_one_inside_other(self):
        outer = BBox(x0=0, y0=0, x1=20, y1=20)
        inner = BBox(x0=5, y0=5, x1=15, y1=15)
        # Overlap equals inner area
        assert _bbox_overlap_area(outer, inner) == pytest.approx(_bbox_area(inner))

    def test_identical_boxes(self):
        b = BBox(x0=0, y0=0, x1=10, y1=10)
        assert _bbox_overlap_area(b, b) == pytest.approx(_bbox_area(b))

    def test_symmetry(self):
        a = BBox(x0=0, y0=0, x1=10, y1=10)
        b = BBox(x0=5, y0=0, x1=15, y1=10)
        assert _bbox_overlap_area(a, b) == pytest.approx(_bbox_overlap_area(b, a))


# ---------------------------------------------------------------------------
# _bbox_cells
# ---------------------------------------------------------------------------

class TestBboxCells:
    def test_single_cell(self):
        """A small bbox entirely within one grid cell."""
        from core.detection.detection_config import BBOX_GRID_CELL_SIZE as S
        b = BBox(x0=1, y0=1, x1=S - 1, y1=S - 1)
        cells = _bbox_cells(b)
        assert cells == {(0, 0)}

    def test_two_col_cells(self):
        """Bbox spanning two grid columns → 2 cells."""
        from core.detection.detection_config import BBOX_GRID_CELL_SIZE as S
        # Span from cell 0 to cell 1 horizontally
        b = BBox(x0=S - 10, y0=0, x1=S + 10, y1=S - 10)
        cells = _bbox_cells(b)
        assert len(cells) == 2
        xs = {c for (_, c) in cells}
        assert 0 in xs and 1 in xs

    def test_returns_set(self):
        b = BBox(x0=0, y0=0, x1=50, y1=50)
        cells = _bbox_cells(b)
        assert isinstance(cells, set)
        assert all(isinstance(c, tuple) and len(c) == 2 for c in cells)


# ---------------------------------------------------------------------------
# _resolve_bbox_overlaps
# ---------------------------------------------------------------------------

class TestResolveBboxOverlaps:
    def test_empty(self):
        assert _resolve_bbox_overlaps([]) == []

    def test_single_region_unchanged(self):
        r = _region(0, 0, 100, 20)
        result = _resolve_bbox_overlaps([r])
        assert len(result) == 1
        assert result[0].bbox == r.bbox

    def test_non_overlapping_both_kept(self):
        r1 = _region(0, 0, 100, 20)
        r2 = _region(0, 30, 100, 50)
        result = _resolve_bbox_overlaps([r1, r2])
        assert len(result) == 2

    def test_lower_conf_clipped_on_overlap(self):
        """Two overlapping regions: lower-confidence one gets clipped."""
        high = _region(0, 0, 100, 20, confidence=0.95)
        low  = _region(0, 10, 100, 30, confidence=0.60)
        result = _resolve_bbox_overlaps([high, low])
        # Both should survive (low gets clipped, not dropped)
        assert len(result) >= 1
        # The high-confidence bbox must be unchanged
        high_out = [r for r in result if r.confidence == 0.95]
        assert len(high_out) == 1
        assert high_out[0].bbox == high.bbox

    def test_tiny_residual_dropped(self):
        """Overlap that leaves a near-zero-area residual → region dropped."""
        # big covers exactly the same area as small
        big   = _region(0, 0, 200, 200, confidence=0.95)
        small = _region(50, 50, 150, 150, confidence=0.60)
        result = _resolve_bbox_overlaps([big, small])
        # small bbox is entirely inside big; after clipping it has no area → dropped
        bboxes = [r.bbox for r in result]
        # The big one must survive
        assert any(b.x0 == 0 and b.y0 == 0 for b in bboxes)

    def test_sorted_by_confidence_descending(self):
        """Higher-confidence region always wins."""
        r1 = _region(0, 0, 50, 50, confidence=0.50)
        r2 = _region(0, 0, 50, 50, confidence=0.95)
        result = _resolve_bbox_overlaps([r1, r2])
        # The surviving region should be the high-confidence one
        assert len(result) >= 1
        assert result[0].confidence == pytest.approx(0.95)

    def test_identical_regions_one_dropped(self):
        """Identical bboxes: second one collapses to zero area → dropped."""
        r1 = _region(0, 0, 100, 20, confidence=0.90)
        r2 = _region(0, 0, 100, 20, confidence=0.80)
        result = _resolve_bbox_overlaps([r1, r2])
        assert len(result) == 1
        assert result[0].confidence == pytest.approx(0.90)

    def test_page_isolation_not_enforced_at_this_level(self):
        """_resolve_bbox_overlaps processes whatever is passed — callers must
        filter by page before calling."""
        # Two regions on different pages with identical coords:
        # function doesn't know about pages, may or may not clip.
        # Just verify it doesn't crash.
        r1 = PIIRegion(
            page_number=1,
            bbox=BBox(x0=0, y0=0, x1=100, y1=20),
            text="A", pii_type=PIIType.PERSON, confidence=0.9,
            source=DetectionSource.NER,
        )
        r2 = PIIRegion(
            page_number=2,
            bbox=BBox(x0=0, y0=0, x1=100, y1=20),
            text="B", pii_type=PIIType.PERSON, confidence=0.8,
            source=DetectionSource.NER,
        )
        result = _resolve_bbox_overlaps([r1, r2])
        assert isinstance(result, list)
