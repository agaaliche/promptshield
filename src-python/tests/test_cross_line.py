"""Tests for core.detection.cross_line — ORG spans that straddle line breaks."""

from __future__ import annotations

import pytest

from core.detection.cross_line import _detect_cross_line_orgs
from models.schemas import PIIType


class TestDetectCrossLineOrgs:
    def test_empty_string(self):
        assert _detect_cross_line_orgs("") == []

    def test_no_newlines(self):
        """No line breaks → no cross-line candidates, empty result."""
        assert _detect_cross_line_orgs("CLUB NAUTIQUE JACQUES-CARTIER INC.") == []

    def test_org_straddling_newline(self):
        """Company name split across a newline is detected."""
        text = "CLUB NAUTIQUE\nJACQUES-CARTIER INC."
        results = _detect_cross_line_orgs(text)
        assert len(results) >= 1
        match = results[0]
        assert match.pii_type == PIIType.ORG
        # The match must span the newline position (13)
        assert match.start <= 13 < match.end
        assert "NAUTIQUE" in match.text or "CLUB" in match.text

    def test_org_not_straddling_is_excluded(self):
        """An ORG that exists entirely on one side of a newline is NOT returned."""
        # "TECHNO LTD" is fully on line 2 → no NL crossing
        text = "Some text here\nTECHNO LTD."
        results = _detect_cross_line_orgs(text)
        # Any result must straddle the boundary at position 14
        nl_pos = text.index("\n")
        for r in results:
            assert r.start <= nl_pos < r.end, \
                f"Non-straddling match leaked: {r!r}"

    def test_result_positions_within_full_text(self):
        """Returned start/end must be valid full_text positions."""
        text = "CLUB NAUTIQUE\nJACQUES-CARTIER INC."
        results = _detect_cross_line_orgs(text)
        for r in results:
            assert 0 <= r.start < len(text)
            assert r.end <= len(text)
            assert r.text == text[r.start:r.end]

    def test_result_text_matches_full_text_slice(self):
        """result.text must equal full_text[start:end]."""
        text = "AGENCE NAUTIQUE\nMONTREAL INC."
        results = _detect_cross_line_orgs(text)
        for r in results:
            assert r.text == text[r.start:r.end]

    def test_deduplicated(self):
        """Duplicate matches at same (start, end) are removed."""
        # Construct a text that may trigger two pattern rules for the same span
        text = "TRANSPORT CANADA\nCORP."
        results = _detect_cross_line_orgs(text)
        spans = [(r.start, r.end) for r in results]
        assert len(spans) == len(set(spans)), "Duplicate spans found"

    def test_confidence_float(self):
        """All returned matches must have a numeric confidence in [0, 1]."""
        text = "CLUB NAUTIQUE\nJACQUES-CARTIER INC."
        results = _detect_cross_line_orgs(text)
        for r in results:
            assert 0.0 <= r.confidence <= 1.0

    def test_multiple_newlines_only_matches_straddling(self):
        """Text with multiple newlines: each match must straddle its own boundary."""
        text = "Preamble text here\nCLUB NAUTIQUE\nJACQUES INC.\nEpilogue text"
        results = _detect_cross_line_orgs(text)
        nl_positions = [i for i, ch in enumerate(text) if ch == "\n"]
        for r in results:
            straddles = any(r.start <= nl < r.end for nl in nl_positions)
            assert straddles, f"Match {r!r} doesn't straddle any newline"
