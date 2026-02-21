"""Tests for core.detection.layout — column detection and detection-text building."""

from __future__ import annotations

import pytest

from core.detection.layout import (
    ColumnBand,
    OffsetMap,
    _std,
    detect_column_bands,
    build_detection_text,
    translate_match,
)
from core.detection.regex_detector import RegexMatch
from core.detection.block_offsets import _compute_block_offsets
from models.schemas import BBox, PageData, PIIType, TextBlock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block(text: str, x0: float, y0: float, x1: float, y1: float) -> TextBlock:
    return TextBlock(
        text=text,
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        confidence=1.0,
        is_ocr=False,
    )


def _page(blocks: list[TextBlock], full_text: str) -> PageData:
    return PageData(
        page_number=1,
        width=595.0,
        height=842.0,
        bitmap_path="",
        text_blocks=blocks,
        full_text=full_text,
    )


# ---------------------------------------------------------------------------
# _std
# ---------------------------------------------------------------------------

class TestStd:
    def test_empty(self):
        assert _std([]) == 0.0

    def test_single(self):
        assert _std([5.0]) == 0.0

    def test_identical(self):
        assert _std([3.0, 3.0, 3.0]) == 0.0

    def test_known(self):
        # std of [0, 0, 4, 4] = sqrt(4) = 2
        assert abs(_std([0.0, 0.0, 4.0, 4.0]) - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# detect_column_bands
# ---------------------------------------------------------------------------

class TestDetectColumnBands:
    def test_empty(self):
        assert detect_column_bands([], 595.0) == []

    def test_single_column_no_gaps(self):
        """Words all in a single tight column — should produce exactly one band."""
        blocks = [
            _block("CLUB",     72, 100, 110, 114),
            _block("NAUTIQUE", 72, 116, 150, 130),
        ]
        bands = detect_column_bands(blocks, 595.0)
        assert len(bands) == 1
        assert all(b.blocks for b in bands)

    def test_two_clear_columns(self):
        """Two columns with large x-gap confirmed on multiple lines."""
        # Column 1: x≈72,  Column 2: x≈310
        # 3 lines each — sufficient votes
        blocks = [
            # Line 1
            _block("Nom:",    72,  50,  110, 62),
            _block("MARTIN",  310, 50,  380, 62),
            # Line 2
            _block("Addr:",   72,  66,  110, 78),
            _block("9,",      310, 66,  325, 78),
            # Line 3
            _block("City:",   72,  82,  110, 94),
            _block("Gatineau",310, 82,  400, 94),
        ]
        bands = detect_column_bands(blocks, 595.0)
        assert len(bands) == 2, f"Expected 2 bands, got {len(bands)}"
        # First band should contain "left" blocks, second "right" blocks
        left_texts = {b.text for b in bands[0].blocks}
        right_texts = {b.text for b in bands[1].blocks}
        assert "Nom:" in left_texts
        assert "MARTIN" in right_texts

    def test_single_line_columns(self):
        """One-line columns — four words in a row separated by large gaps."""
        blocks = [
            _block("Nom:",     72,  50, 110, 62),
            _block("MARTIN",   200, 50, 270, 62),
            _block("Date:",    380, 50, 415, 62),
            _block("2024",     480, 50, 520, 62),
        ]
        bands = detect_column_bands(blocks, 595.0)
        # Single line means only 1 vote per gap → confirmed only if _COL_MIN_LINE_VOTES==1
        # With default of 2, single-line should fall through to one band.
        # (This is correct behaviour: we can't confirm structure from one line.)
        assert len(bands) >= 1
        assert sum(len(b.blocks) for b in bands) == len(blocks)

    def test_all_blocks_assigned(self):
        """Every block must appear in exactly one band."""
        blocks = [
            _block("A", 72,  50, 90, 62),
            _block("B", 300, 50, 380, 62),
            _block("C", 72,  66, 110, 78),
            _block("D", 300, 66, 380, 78),
            _block("E", 72,  82, 90, 94),
            _block("F", 300, 82, 380, 94),
        ]
        bands = detect_column_bands(blocks, 595.0)
        assigned = [b for band in bands for b in band.blocks]
        assert len(assigned) == len(blocks)


# ---------------------------------------------------------------------------
# build_detection_text
# ---------------------------------------------------------------------------

class TestBuildDetectionText:
    def test_empty_page(self):
        page = _page([], "")
        om = build_detection_text(page, [])
        assert om.detection_text == ""

    def test_single_block(self):
        """Single word — detection_text equals the word."""
        blk = _block("MARTIN", 72, 50, 130, 62)
        page = _page([blk], "MARTIN")
        bo = _compute_block_offsets([blk], "MARTIN")
        om = build_detection_text(page, bo)
        assert om.detection_text == "MARTIN"
        # All positions should map to full_text[0..5]
        assert om.dt_to_ft == [0, 1, 2, 3, 4, 5]

    def test_cross_line_join_with_space(self):
        """Two consecutive lines in a single column are joined with a space."""
        #  full_text: "CLUB NAUTIQUE\nJACQUES-CARTIER"
        # Word blocks (approx):
        blk_club     = _block("CLUB",             72, 100, 110, 112)
        blk_nautique = _block("NAUTIQUE",          115, 100, 185, 112)
        blk_jacques  = _block("JACQUES-CARTIER",   72, 116, 200, 128)
        full_text = "CLUB NAUTIQUE\nJACQUES-CARTIER"
        page = _page(
            [blk_club, blk_nautique, blk_jacques],
            full_text,
        )
        bo = _compute_block_offsets(
            [blk_club, blk_nautique, blk_jacques], full_text,
        )
        om = build_detection_text(page, bo)
        # The newline between lines must be replaced by a space
        assert "\n" not in om.detection_text
        assert "CLUB" in om.detection_text
        assert "NAUTIQUE" in om.detection_text
        assert "JACQUES-CARTIER" in om.detection_text
        # The three words should be space-separated in one run
        assert "NAUTIQUE JACQUES-CARTIER" in om.detection_text

    def test_paragraph_break_kept(self):
        """Lines with a large y-gap inside one column keep a newline."""
        blk_a = _block("TITRE",     72, 50,  130, 62)    # line 1
        blk_b = _block("Contenu",   72, 200, 160, 212)   # line 2 — 138 pts gap, avg_h≈12
        full_text = "TITRE\nContenu"
        page = _page([blk_a, blk_b], full_text)
        bo = _compute_block_offsets([blk_a, blk_b], full_text)
        om = build_detection_text(page, bo)
        # Large gap → paragraph break → newline preserved
        assert "\n" in om.detection_text

    def test_dt_to_ft_length_matches(self):
        """dt_to_ft must have same length as detection_text."""
        blk1 = _block("Hello", 72, 50, 110, 62)
        blk2 = _block("World", 72, 66, 110, 78)
        ft = "Hello\nWorld"
        page = _page([blk1, blk2], ft)
        bo = _compute_block_offsets([blk1, blk2], ft)
        om = build_detection_text(page, bo)
        assert len(om.detection_text) == len(om.dt_to_ft)

    def test_word_chars_map_to_correct_ft_positions(self):
        """Characters from words must map to their full_text positions."""
        blk = _block("ABC", 72, 50, 90, 62)
        ft = "ABC"
        page = _page([blk], ft)
        bo = _compute_block_offsets([blk], ft)
        om = build_detection_text(page, bo)
        for i, ch in enumerate(blk.text):
            assert om.detection_text[om.dt_to_ft.index(i)] == ch


# ---------------------------------------------------------------------------
# translate_match
# ---------------------------------------------------------------------------

class TestTranslateMatch:
    """Test match translation from detection_text → full_text coordinates."""

    def _make_match(self, start: int, end: int, text: str) -> RegexMatch:
        return RegexMatch(
            start=start, end=end, text=text,
            pii_type=PIIType.ORG, confidence=0.9,
        )

    def test_identity_no_separators(self):
        """Match that covers only real ft chars — positions unchanged."""
        full_text = "MARTIN"
        dt_to_ft = [0, 1, 2, 3, 4, 5]
        m = self._make_match(0, 6, "MARTIN")
        tm = translate_match(m, dt_to_ft, full_text)
        assert tm is not None
        assert tm.start == 0
        assert tm.end == 6
        assert tm.text == "MARTIN"

    def test_cross_line_match_translated(self):
        """Match spanning two lines: \\n in ft-text normalised to space."""
        # full_text: "CLUB NAUTIQUE\nJACQUES"
        # detection_text: "CLUB NAUTIQUE JACQUES" (\\n → space)
        full_text = "CLUB NAUTIQUE\nJACQUES"
        # dt_to_ft: real chars at ft positions, separator at ft=13 (\\n pos) → -1
        dt_to_ft = (
            [0, 1, 2, 3]         # CLUB
            + [-1]               # space sep
            + [5, 6, 7, 8, 9, 10, 11, 12]  # NAUTIQUE
            + [-1]               # space (was \\n at ft=13)
            + [14, 15, 16, 17, 18, 19, 20]  # JACQUES
        )
        # Match "NAUTIQUE JACQUES" in detection text starting at position 5
        m = self._make_match(5, 21, "NAUTIQUE JACQUES")
        tm = translate_match(m, dt_to_ft, full_text)
        assert tm is not None
        assert tm.start == 5           # ft position of 'N' in NAUTIQUE
        assert tm.end == 21            # ft position after last char of JACQUES
        assert "\n" not in tm.text
        assert "NAUTIQUE" in tm.text
        assert "JACQUES" in tm.text

    def test_returns_none_for_all_separators(self):
        """If match covers only -1 positions, return None."""
        full_text = "A B"
        dt_to_ft = [0, -1, 2]
        m = self._make_match(1, 2, " ")  # matches the inserted space
        tm = translate_match(m, dt_to_ft, full_text)
        assert tm is None

    def test_single_char_match(self):
        """Single character match."""
        full_text = "XY"
        dt_to_ft = [0, 1]
        m = self._make_match(0, 1, "X")
        tm = translate_match(m, dt_to_ft, full_text)
        assert tm is not None
        assert tm.start == 0
        assert tm.end == 1
        assert tm.text == "X"

    def test_newline_in_ft_text_normalised(self):
        """Embedded \\n in full_text slice is replaced by space in tm.text."""
        full_text = "A\nB"
        dt_to_ft = [0, -1, 2]
        m = self._make_match(0, 3, "A B")
        tm = translate_match(m, dt_to_ft, full_text)
        assert tm is not None
        assert tm.text == "A B"  # \\n replaced by space
        assert tm.start == 0
        assert tm.end == 3
