"""Tests for the char-offset → bbox mapping that drives region alignment.

Verifies that _compute_block_offsets and _char_offset_to_bbox correctly
map PII character spans to spatial bounding boxes on the page.
"""

import pytest
from models.schemas import BBox, TextBlock
from core.detection.pipeline import (
    _compute_block_offsets,
    _char_offset_to_bbox,
)
from core.ingestion.loader import _build_full_text, _cluster_into_lines


# ── Helpers ──────────────────────────────────────────────────────────

def _tb(text: str, x0: float, y0: float, x1: float, y1: float) -> TextBlock:
    """Create a TextBlock shorthand."""
    return TextBlock(
        text=text,
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        confidence=1.0,
        block_index=0,
        line_index=0,
        word_index=0,
        is_ocr=False,
    )


# ── TestClusterIntoLines ─────────────────────────────────────────────

class TestClusterIntoLines:
    """Verify that text blocks are grouped into correct visual lines."""

    def test_single_line(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
        ]
        lines = _cluster_into_lines(blocks)
        assert len(lines) == 1
        assert [b.text for b in lines[0]] == ["Hello", "World"]

    def test_two_lines(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
            _tb("Foo", 50, 120, 80, 132),
            _tb("Bar", 90, 120, 120, 132),
        ]
        lines = _cluster_into_lines(blocks)
        assert len(lines) == 2
        assert [b.text for b in lines[0]] == ["Hello", "World"]
        assert [b.text for b in lines[1]] == ["Foo", "Bar"]

    def test_noisy_y_same_line(self):
        """Words on the same line with slightly different y0 values
        (common with ascenders/descenders or OCR noise)."""
        blocks = [
            _tb("Hello", 50, 100.5, 100, 112.5),
            _tb("World", 110, 100.0, 160, 112.0),
            _tb("Test", 170, 100.8, 200, 112.8),
        ]
        lines = _cluster_into_lines(blocks)
        assert len(lines) == 1
        # Should sort by x0 within the line
        assert [b.text for b in lines[0]] == ["Hello", "World", "Test"]

    def test_sort_within_line(self):
        """Blocks already in reverse x-order should be re-sorted."""
        blocks = [
            _tb("World", 110, 100, 160, 112),
            _tb("Hello", 50, 100, 100, 112),
        ]
        lines = _cluster_into_lines(blocks)
        assert len(lines) == 1
        assert [b.text for b in lines[0]] == ["Hello", "World"]


# ── TestBuildFullText ────────────────────────────────────────────────

class TestBuildFullText:
    """Verify full_text construction from text blocks."""

    def test_single_line(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
        ]
        text = _build_full_text(blocks)
        assert text == "Hello World"

    def test_two_lines(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
            _tb("Foo", 50, 120, 80, 132),
        ]
        text = _build_full_text(blocks)
        # Gap between lines: 120 - 100 = 20 > 12*0.6 = 7.2 → newline
        assert text == "Hello World\nFoo"

    def test_empty_blocks(self):
        assert _build_full_text([]) == ""

    def test_single_block(self):
        blocks = [_tb("Hello", 50, 100, 100, 112)]
        text = _build_full_text(blocks)
        assert text == "Hello"


# ── TestComputeBlockOffsets ──────────────────────────────────────────

class TestComputeBlockOffsets:
    """Verify deterministic offset computation matches full_text."""

    def test_single_line_offsets(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        assert len(offsets) == 2
        # "Hello World" → Hello at [0,5), World at [6,11)
        assert offsets[0][0] == 0
        assert offsets[0][1] == 5
        assert offsets[0][2].text == "Hello"
        assert offsets[1][0] == 6
        assert offsets[1][1] == 11
        assert offsets[1][2].text == "World"
        # Verify against full_text
        for start, end, block in offsets:
            assert full_text[start:end] == block.text

    def test_multiline_offsets(self):
        blocks = [
            _tb("John", 50, 100, 90, 112),
            _tb("Smith", 100, 100, 150, 112),
            _tb("123", 50, 125, 75, 137),
            _tb("Main", 80, 125, 120, 137),
            _tb("Street", 125, 125, 180, 137),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        assert len(offsets) == 5
        # Verify all offsets match full_text
        for start, end, block in offsets:
            assert full_text[start:end] == block.text, (
                f"Mismatch: full_text[{start}:{end}] = "
                f"'{full_text[start:end]}' != '{block.text}'"
            )

    def test_duplicate_words(self):
        """Duplicate words (like 'the') should not confuse offset computation."""
        blocks = [
            _tb("the", 50, 100, 70, 112),
            _tb("cat", 80, 100, 100, 112),
            _tb("and", 110, 100, 140, 112),
            _tb("the", 150, 100, 170, 112),
            _tb("dog", 180, 100, 210, 112),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        assert len(offsets) == 5
        for start, end, block in offsets:
            assert full_text[start:end] == block.text

        # Specifically check both "the" blocks map to different positions
        the1_start, the1_end, _ = offsets[0]
        the2_start, the2_end, _ = offsets[3]
        assert the1_start != the2_start
        assert full_text[the1_start:the1_end] == "the"
        assert full_text[the2_start:the2_end] == "the"

    def test_unsorted_input(self):
        """Blocks given in arbitrary order should still produce correct offsets."""
        # Provide blocks in reverse order
        blocks = [
            _tb("Bar", 90, 120, 120, 132),        # line 2, word 2
            _tb("Hello", 50, 100, 100, 112),       # line 1, word 1
            _tb("Foo", 50, 120, 80, 132),           # line 2, word 1
            _tb("World", 110, 100, 160, 112),       # line 1, word 2
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        for start, end, block in offsets:
            assert full_text[start:end] == block.text

    def test_noisy_y_coordinates(self):
        """OCR noise in y-positions should still align correctly."""
        blocks = [
            _tb("Hello", 50, 100.5, 100, 112.5),
            _tb("World", 110, 100.0, 160, 112.0),
            _tb("Test", 170, 100.8, 200, 112.8),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        for start, end, block in offsets:
            assert full_text[start:end] == block.text


# ── TestCharOffsetToBBox ─────────────────────────────────────────────

class TestCharOffsetToBBox:
    """Verify character offset → bounding box mapping."""

    def test_single_word(self):
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        bbox = _char_offset_to_bbox(0, 5, offsets)  # "Hello"
        assert bbox is not None
        assert bbox.x0 == 50
        assert bbox.y0 == 100
        assert bbox.x1 == 100
        assert bbox.y1 == 112

    def test_multi_word_span(self):
        """A span covering multiple words should merge their bboxes."""
        blocks = [
            _tb("John", 50, 100, 90, 112),
            _tb("Smith", 100, 100, 155, 112),
        ]
        full_text = _build_full_text(blocks)  # "John Smith"
        offsets = _compute_block_offsets(blocks, full_text)

        bbox = _char_offset_to_bbox(0, 10, offsets)  # "John Smith"
        assert bbox is not None
        assert bbox.x0 == 50
        assert bbox.x1 == 155

    def test_multiline_span(self):
        """A span crossing a line boundary should merge bboxes from both lines."""
        blocks = [
            _tb("John", 50, 100, 90, 112),
            _tb("Smith", 100, 100, 155, 112),
            _tb("123", 50, 130, 75, 142),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        # "Smith\n123" spans across the newline
        idx_smith = full_text.index("Smith")
        idx_123_end = full_text.index("123") + 3
        bbox = _char_offset_to_bbox(idx_smith, idx_123_end, offsets)
        assert bbox is not None
        assert bbox.y0 == 100   # top of Smith line
        assert bbox.y1 == 142   # bottom of 123 line

    def test_second_occurrence_of_duplicate_word(self):
        """Mapping the second 'the' should point to the correct bbox."""
        blocks = [
            _tb("the", 50, 100, 70, 112),
            _tb("cat", 80, 100, 110, 112),
            _tb("the", 150, 100, 170, 112),
            _tb("dog", 180, 100, 210, 112),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        # Find the second "the"
        second_the_start = full_text.index("the", 4)
        bbox = _char_offset_to_bbox(
            second_the_start, second_the_start + 3, offsets
        )
        assert bbox is not None
        assert bbox.x0 == 150  # the second "the" block

    def test_fallback_closest_block(self):
        """If char range doesn't overlap any block, fallback to nearest."""
        blocks = [
            _tb("Hello", 50, 100, 100, 112),
            _tb("World", 110, 100, 160, 112),
        ]
        full_text = _build_full_text(blocks)
        offsets = _compute_block_offsets(blocks, full_text)

        # Offset way past the end
        bbox = _char_offset_to_bbox(999, 1005, offsets)
        assert bbox is not None  # should return something rather than None

    def test_empty_blocks(self):
        bbox = _char_offset_to_bbox(0, 5, [])
        assert bbox is None
