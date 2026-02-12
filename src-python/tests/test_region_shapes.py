"""Tests for region shape enforcement in the detection pipeline."""

import pytest

spacy = pytest.importorskip("spacy", reason="spaCy not installed")

from models.schemas import (
    BBox, TextBlock, PageData, PIIRegion, PIIType, DetectionSource,
)
from core.detection.pipeline import (
    _clamp_bbox,
    _blocks_overlapping_bbox,
    _split_blocks_at_gaps,
    _bbox_from_block_triples,
    _enforce_region_shapes,
    _effective_gap_threshold,
    _char_offsets_to_line_bboxes,
    _ABSOLUTE_MAX_GAP_PX,
    _GAP_OUTLIER_FACTOR,
    _MAX_WORD_GAP_WS,
    _MAX_WORDS_PER_REGION,
)
from core.config import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tb(text: str, x0: float, y0: float, x1: float, y1: float) -> TextBlock:
    """Shortcut to create a TextBlock."""
    return TextBlock(text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def _region(
    bbox: BBox,
    text: str = "test",
    pii_type: PIIType = PIIType.PERSON,
    confidence: float = 0.9,
    char_start: int = 0,
    char_end: int = 4,
    page_number: int = 1,
) -> PIIRegion:
    return PIIRegion(
        page_number=page_number,
        bbox=bbox,
        text=text,
        pii_type=pii_type,
        confidence=confidence,
        source=DetectionSource.NER,
        char_start=char_start,
        char_end=char_end,
    )


# ---------------------------------------------------------------------------
# _clamp_bbox
# ---------------------------------------------------------------------------

class TestClampBBox:
    def test_within_bounds(self):
        bbox = BBox(x0=10, y0=20, x1=100, y1=50)
        clamped = _clamp_bbox(bbox, 612, 792)
        assert clamped == bbox

    def test_exceeds_right(self):
        bbox = BBox(x0=10, y0=20, x1=700, y1=50)
        clamped = _clamp_bbox(bbox, 612, 792)
        assert clamped.x1 == 612

    def test_exceeds_bottom(self):
        bbox = BBox(x0=10, y0=20, x1=100, y1=900)
        clamped = _clamp_bbox(bbox, 612, 792)
        assert clamped.y1 == 792

    def test_negative_coords(self):
        bbox = BBox(x0=-5, y0=-3, x1=100, y1=50)
        clamped = _clamp_bbox(bbox, 612, 792)
        assert clamped.x0 == 0.0
        assert clamped.y0 == 0.0


# ---------------------------------------------------------------------------
# _blocks_overlapping_bbox
# ---------------------------------------------------------------------------

class TestBlocksOverlappingBBox:
    def test_finds_overlapping(self):
        blocks = [
            _tb("hello", 10, 10, 50, 20),
            _tb("world", 60, 10, 100, 20),
            _tb("other", 200, 200, 250, 210),
        ]
        offsets = [(0, 5, blocks[0]), (6, 11, blocks[1]), (12, 17, blocks[2])]
        bbox = BBox(x0=5, y0=5, x1=110, y1=25)
        result = _blocks_overlapping_bbox(bbox, offsets)
        assert len(result) == 2

    def test_no_overlap(self):
        blocks = [_tb("hello", 200, 200, 250, 210)]
        offsets = [(0, 5, blocks[0])]
        bbox = BBox(x0=10, y0=10, x1=50, y1=20)
        result = _blocks_overlapping_bbox(bbox, offsets)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _effective_gap_threshold
# ---------------------------------------------------------------------------

class TestEffectiveGapThreshold:
    def setup_method(self):
        self._orig = config.detection_fuzziness

    def teardown_method(self):
        config.detection_fuzziness = self._orig

    def test_strict(self):
        config.detection_fuzziness = 0.0
        # At fuzziness=0, ratio=0.50 → 12pt font → 6.0pt
        assert abs(_effective_gap_threshold(12.0) - 6.0) < 0.01

    def test_permissive(self):
        config.detection_fuzziness = 1.0
        # At fuzziness=1, ratio=1.25 → 12pt font → 15.0pt
        assert abs(_effective_gap_threshold(12.0) - 15.0) < 0.01

    def test_default(self):
        config.detection_fuzziness = 0.5
        # ratio=0.875 → 12pt font → 10.5pt
        assert abs(_effective_gap_threshold(12.0) - 10.5) < 0.01

    def test_absolute_cap(self):
        config.detection_fuzziness = 1.0
        # 30pt line height → ratio=1.0 → 30pt but capped at 20
        assert _effective_gap_threshold(30.0) == _ABSOLUTE_MAX_GAP_PX


# ---------------------------------------------------------------------------
# _split_blocks_at_gaps
# ---------------------------------------------------------------------------

class TestSplitBlocksAtGaps:
    def setup_method(self):
        """Pin fuzziness to 0.5 for deterministic tests."""
        self._orig = config.detection_fuzziness
        config.detection_fuzziness = 0.5

    def teardown_method(self):
        config.detection_fuzziness = self._orig

    def test_no_split_close_blocks(self):
        b1 = _tb("John", 10, 10, 40, 20)
        b2 = _tb("Smith", 44, 10, 80, 20)  # 4pt gap, threshold ~7pt
        triples = [(0, 4, b1), (5, 10, b2)]
        result = _split_blocks_at_gaps(triples, "John Smith")
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_split_large_spatial_gap(self):
        b1 = _tb("John", 10, 10, 40, 20)
        b2 = _tb("Smith", 50, 10, 80, 20)  # 10pt gap > 7pt threshold
        triples = [(0, 4, b1), (5, 10, b2)]
        result = _split_blocks_at_gaps(triples, "John Smith")
        assert len(result) == 2

    def test_split_large_whitespace_gap(self):
        b1 = _tb("John", 10, 10, 40, 20)
        b2 = _tb("Smith", 44, 10, 80, 20)
        # 4 whitespace chars between blocks in full_text
        full_text = "John    Smith"
        triples = [(0, 4, b1), (8, 13, b2)]
        result = _split_blocks_at_gaps(triples, full_text)
        assert len(result) == 2

    def test_single_block(self):
        b1 = _tb("Hello", 10, 10, 50, 20)
        triples = [(0, 5, b1)]
        result = _split_blocks_at_gaps(triples, "Hello")
        assert len(result) == 1

    def test_empty(self):
        result = _split_blocks_at_gaps([], "")
        assert result == []

    def test_uniform_gaps_no_split(self):
        """Uniform word gaps should NOT split even when slightly above
        the absolute threshold — the outlier check prevents it.
        This is the '91269270 Canada Inc' bug fix.
        """
        config.detection_fuzziness = 0.0  # strict: threshold = 0.5 × 10 = 5pt
        # All gaps ~6pt — each above the 5pt threshold but uniform
        b1 = _tb("91269270", 10, 10, 60, 20)
        b2 = _tb("Canada", 66, 10, 100, 20)   # 6pt gap
        b3 = _tb("Inc", 107, 10, 125, 20)      # 7pt gap
        triples = [(0, 8, b1), (9, 15, b2), (16, 19, b3)]
        result = _split_blocks_at_gaps(triples, "91269270 Canada Inc")
        # 7pt < 6pt × 3.0 = 18pt → not outlier → no split
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_outlier_gap_splits(self):
        """A truly large gap (column separator) should still split."""
        config.detection_fuzziness = 0.0  # strict threshold = 5pt
        b1 = _tb("John", 10, 10, 40, 20)       # word 1
        b2 = _tb("Smith", 45, 10, 80, 20)       # 5pt gap (normal)
        b3 = _tb("DOB", 120, 10, 145, 20)       # 40pt gap (column)
        triples = [(0, 4, b1), (5, 10, b2), (11, 14, b3)]
        result = _split_blocks_at_gaps(triples, "John Smith DOB")
        # 40pt > 5pt × 3.0 = 15pt → outlier → splits
        assert len(result) == 2
        assert len(result[0]) == 2  # John Smith
        assert len(result[1]) == 1  # DOB


# ---------------------------------------------------------------------------
# _enforce_region_shapes
# ---------------------------------------------------------------------------

class TestEnforceRegionShapes:
    def _make_page_data(
        self, blocks: list[TextBlock], full_text: str,
        width: float = 612, height: float = 792,
    ) -> PageData:
        return PageData(
            page_number=1,
            width=width,
            height=height,
            bitmap_path="",
            text_blocks=blocks,
            full_text=full_text,
        )

    def test_passthrough_small_region(self):
        """Region with ≤4 words and no gaps passes through unchanged."""
        b1 = _tb("John", 10, 10, 40, 20)
        b2 = _tb("Smith", 44, 10, 80, 20)
        blocks = [b1, b2]
        offsets = [(0, 4, b1), (5, 10, b2)]
        page = self._make_page_data(blocks, "John Smith")

        r = _region(BBox(x0=10, y0=10, x1=80, y1=20), text="John Smith",
                     char_start=0, char_end=10)
        result = _enforce_region_shapes([r], page, offsets)
        assert len(result) == 1
        assert result[0].text == "John Smith"

    def test_clamp_out_of_bounds(self):
        """Region outside page bounds is clamped."""
        b1 = _tb("Test", 600, 10, 650, 20)
        offsets = [(0, 4, b1)]
        page = self._make_page_data([b1], "Test", width=612)

        r = _region(BBox(x0=600, y0=10, x1=650, y1=20), text="Test",
                     char_start=0, char_end=4)
        result = _enforce_region_shapes([r], page, offsets)
        assert len(result) == 1
        assert result[0].bbox.x1 == 612

    def test_degenerate_removed(self):
        """Region that becomes degenerate (< 1pt) after clamping is dropped."""
        b1 = _tb("X", 615, 10, 620, 20)
        offsets = [(0, 1, b1)]
        page = self._make_page_data([b1], "X", width=612)

        r = _region(BBox(x0=615, y0=10, x1=620, y1=20), text="X",
                     char_start=0, char_end=1)
        result = _enforce_region_shapes([r], page, offsets)
        # After clamping x0=612, x1=612 → width < 1 → dropped
        assert len(result) == 0

    def test_gap_split(self):
        """Region with large gap between words is split into two."""
        b1 = _tb("John", 10, 10, 40, 20)
        b2 = _tb("Smith", 50, 10, 80, 20)  # 10pt gap
        offsets = [(0, 4, b1), (5, 10, b2)]
        page = self._make_page_data([b1, b2], "John Smith")

        r = _region(BBox(x0=10, y0=10, x1=80, y1=20), text="John Smith",
                     char_start=0, char_end=10)
        result = _enforce_region_shapes([r], page, offsets)
        assert len(result) == 2

    def test_word_limit_split(self):
        """Region with > 4 words is split into ≤ 4-word chunks."""
        # Create 6 words close together (< 6pt gaps)
        words = ["one", "two", "three", "four", "five", "six"]
        blocks = []
        offsets_list = []
        x = 10
        pos = 0
        for w in words:
            bw = len(w) * 6  # ~6pt per char
            b = _tb(w, x, 10, x + bw, 20)
            blocks.append(b)
            offsets_list.append((pos, pos + len(w), b))
            x += bw + 4  # 4pt gap (within limit)
            pos += len(w) + 1

        full_text = " ".join(words)
        page = self._make_page_data(blocks, full_text)

        overall_bbox = BBox(
            x0=min(b.bbox.x0 for b in blocks),
            y0=10,
            x1=max(b.bbox.x1 for b in blocks),
            y1=20,
        )
        r = _region(overall_bbox, text=full_text,
                     char_start=0, char_end=len(full_text))
        result = _enforce_region_shapes([r], page, offsets_list)
        # 6 words → split into chunks of 4 → 2 chunks (4 + 2)
        assert len(result) == 2
        # Each chunk has at most 4 words
        for reg in result:
            assert len(reg.text.split()) <= _MAX_WORDS_PER_REGION

    def test_manual_region_no_blocks(self):
        """Region with no overlapping blocks (manual draw) passes through."""
        page = self._make_page_data([], "")
        r = _region(BBox(x0=10, y0=10, x1=100, y1=50), text="manual")
        result = _enforce_region_shapes([r], page, [])
        # Empty block_offsets returns early
        assert len(result) == 1

    def test_no_overlapping_blocks_keeps_region(self):
        """Region whose bbox doesn't overlap any blocks is kept as-is."""
        b1 = _tb("far", 500, 500, 530, 510)
        offsets = [(0, 3, b1)]
        page = self._make_page_data([b1], "far")

        r = _region(BBox(x0=10, y0=10, x1=100, y1=20), text="manual")
        result = _enforce_region_shapes([r], page, offsets)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _char_offsets_to_line_bboxes – same-line merge
# ---------------------------------------------------------------------------

class TestCharOffsetsToLineBboxesMerge:
    """Blocks on the same visual line must produce one bbox even when
    _cluster_into_lines over-splits due to slight y-centre differences."""

    def test_same_line_slight_y_drift_produces_one_bbox(self):
        """Simulates '91269270 Canada Inc' where 'Inc' has a slightly
        different y-centre.  All blocks should merge into a single bbox."""
        # Three blocks on roughly the same line, "Inc" shifted down by 2pt
        b1 = _tb("91269270", 100, 200, 160, 210)  # yc=205
        b2 = _tb("Canada",   165, 200, 210, 210)   # yc=205
        b3 = _tb("Inc",      215, 202, 240, 212)   # yc=207 — shifted 2pt

        offsets = [
            (0,  8, b1),  # "91269270"
            (9, 15, b2),  # "Canada"
            (16, 19, b3), # "Inc"
        ]

        bboxes = _char_offsets_to_line_bboxes(0, 19, offsets)

        assert len(bboxes) == 1, (
            f"Expected 1 bbox for single-line entity, got {len(bboxes)}: {bboxes}"
        )
        # The merged bbox should span the full extent
        assert bboxes[0].x0 == 100
        assert bboxes[0].x1 == 240

    def test_genuine_multiline_still_splits(self):
        """Blocks on genuinely different lines should still produce
        multiple bboxes."""
        b1 = _tb("John", 100, 200, 140, 210)    # yc=205, line 1
        b2 = _tb("Smith", 100, 250, 150, 260)   # yc=255, line 2 (50pt away)

        offsets = [
            (0, 4, b1),
            (5, 10, b2),
        ]

        bboxes = _char_offsets_to_line_bboxes(0, 10, offsets)

        assert len(bboxes) == 2, (
            f"Expected 2 bboxes for multi-line entity, got {len(bboxes)}"
        )
