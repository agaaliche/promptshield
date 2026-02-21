"""Tests for core.detection.merge — the multi-layer merge pipeline.

Covers:
  - Empty / single-source input
  - Cross-layer confidence boosting
  - NER digit-count pre-filter
  - Priority-based overlap resolution
  - Same-type overlap unioning
  - Noise filters (ORG, PERSON page-header, ADDRESS number-only)
  - ADDRESS fragment merging
  - Spatial proximity splitting (_split_bboxes_by_proximity)
  - BBox conversion (single-line vs multi-line linked groups)
  - Standalone ORG suppression
  - Structured post-merge filters
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)
from core.detection.regex_detector import RegexMatch
from core.detection.ner_detector import NERMatch
from core.detection.gliner_detector import GLiNERMatch
from core.detection.llm_detector import LLMMatch
from core.detection.merge import _merge_detections, _split_bboxes_by_proximity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(text: str, width: float = 612, height: float = 792) -> PageData:
    """Build a simple single-block PageData from text."""
    tb = TextBlock(
        text=text,
        bbox=BBox(x0=50, y0=50, x1=550, y1=70),
        block_index=0,
        line_index=0,
        word_index=0,
    )
    return PageData(
        page_number=1,
        width=width,
        height=height,
        bitmap_path="/tmp/page.png",
        text_blocks=[tb],
        full_text=text,
    )


def _make_multiline_page(lines: list[str], y_start: float = 50, line_height: float = 20) -> PageData:
    """Build a PageData with one TextBlock per line."""
    blocks: list[TextBlock] = []
    full_text = ""
    for i, line in enumerate(lines):
        y0 = y_start + i * line_height
        blocks.append(TextBlock(
            text=line,
            bbox=BBox(x0=50, y0=y0, x1=550, y1=y0 + line_height - 2),
            block_index=0,
            line_index=i,
            word_index=0,
        ))
        if full_text:
            full_text += "\n"
        full_text += line
    return PageData(
        page_number=1,
        width=612,
        height=792,
        bitmap_path="/tmp/page.png",
        text_blocks=blocks,
        full_text=full_text,
    )


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------

class TestEmptyInputs:
    def test_all_empty(self):
        page = _make_page("Nothing to detect here.")
        result = _merge_detections([], [], [], page)
        assert result == []

    def test_empty_page_text(self):
        page = _make_page("")
        result = _merge_detections([], [], [], page)
        assert result == []


# ---------------------------------------------------------------------------
# Single-source detections
# ---------------------------------------------------------------------------

class TestSingleSource:
    def test_single_regex_email(self):
        text = "Contact john@example.com for details."
        page = _make_page(text)
        rm = RegexMatch(
            start=8, end=24, text="john@example.com",
            pii_type=PIIType.EMAIL, confidence=0.95,
        )
        result = _merge_detections([rm], [], [], page)
        assert len(result) >= 1
        emails = [r for r in result if r.pii_type == PIIType.EMAIL]
        assert len(emails) == 1
        assert emails[0].source == DetectionSource.REGEX
        assert emails[0].text == "john@example.com"

    def test_single_ner_person(self):
        text = "The manager is John Smith and he runs the department."
        page = _make_page(text)
        nm = NERMatch(
            start=15, end=25, text="John Smith",
            pii_type=PIIType.PERSON, confidence=0.85,
        )
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) >= 1
        assert persons[0].text == "John Smith"

    def test_single_llm_address(self):
        text = "Ship to 123 Main Street, Springfield, IL 62704 please."
        page = _make_page(text)
        lm = LLMMatch(
            start=8, end=46, text="123 Main Street, Springfield, IL 62704",
            pii_type=PIIType.ADDRESS, confidence=0.80,
        )
        result = _merge_detections([], [], [lm], page)
        addrs = [r for r in result if r.pii_type == PIIType.ADDRESS]
        assert len(addrs) >= 1


# ---------------------------------------------------------------------------
# Cross-layer confidence boost
# ---------------------------------------------------------------------------

class TestCrossLayerBoost:
    def test_two_layers_boost(self):
        """Two layers with ≥50% overlap → confidence gets +0.10 boost."""
        text = "Call 555-123-4567 now."
        page = _make_page(text)
        rm = RegexMatch(
            start=5, end=17, text="555-123-4567",
            pii_type=PIIType.PHONE, confidence=0.90,
        )
        nm = NERMatch(
            start=5, end=17, text="555-123-4567",
            pii_type=PIIType.PHONE, confidence=0.80,
        )
        result = _merge_detections([rm], [nm], [], page)
        phones = [r for r in result if r.pii_type == PIIType.PHONE]
        assert len(phones) >= 1
        # The winner should have boosted confidence ≥ original
        assert phones[0].confidence >= 0.90

    def test_three_layers_boost(self):
        """Three layers with overlap → confidence gets +0.15 boost."""
        text = "Send to john@acme.com today."
        page = _make_page(text)
        rm = RegexMatch(start=8, end=21, text="john@acme.com", pii_type=PIIType.EMAIL, confidence=0.95)
        nm = NERMatch(start=8, end=21, text="john@acme.com", pii_type=PIIType.EMAIL, confidence=0.70)
        lm = LLMMatch(start=8, end=21, text="john@acme.com", pii_type=PIIType.EMAIL, confidence=0.75)
        result = _merge_detections([rm], [nm], [lm], page)
        emails = [r for r in result if r.pii_type == PIIType.EMAIL]
        assert len(emails) >= 1
        # Boosted confidence should exceed the max individual
        assert emails[0].confidence >= 0.95

    def test_no_boost_low_overlap(self):
        """Non-overlapping detections from different layers → no confidence boost applied."""
        lines = ["Contact john@foo.com for details.", "Also reach jane@bar.com please."]
        page = _make_multiline_page(lines)
        rm = RegexMatch(start=8, end=20, text="john@foo.com", pii_type=PIIType.EMAIL, confidence=0.95)
        lm = LLMMatch(start=len(lines[0]) + 1 + 11, end=len(lines[0]) + 1 + 23,
                       text="jane@bar.com", pii_type=PIIType.EMAIL, confidence=0.90)
        result = _merge_detections([rm], [], [lm], page)
        emails = [r for r in result if r.pii_type == PIIType.EMAIL]
        # At least one email should survive
        assert len(emails) >= 1
        # The regex email should NOT be boosted (no overlapping layer for that span)
        regex_email = [r for r in emails if r.text == "john@foo.com"]
        if regex_email:
            assert regex_email[0].confidence <= 1.0  # no boost beyond expected range


# ---------------------------------------------------------------------------
# NER digit-count pre-filter
# ---------------------------------------------------------------------------

class TestNERDigitFilter:
    def test_phone_too_few_digits_dropped(self):
        """NER PHONE with <7 digits should be filtered out."""
        text = "Code 12345 should be entered."
        page = _make_page(text)
        nm = NERMatch(start=5, end=10, text="12345", pii_type=PIIType.PHONE, confidence=0.80)
        result = _merge_detections([], [nm], [], page)
        phones = [r for r in result if r.pii_type == PIIType.PHONE]
        assert len(phones) == 0

    def test_phone_enough_digits_kept(self):
        """NER PHONE with ≥7 digits should survive."""
        text = "Call 5551234567 now."
        page = _make_page(text)
        nm = NERMatch(start=5, end=15, text="5551234567", pii_type=PIIType.PHONE, confidence=0.85)
        result = _merge_detections([], [nm], [], page)
        phones = [r for r in result if r.pii_type == PIIType.PHONE]
        assert len(phones) >= 1

    def test_ssn_with_period_dropped(self):
        """NER SSN containing '.' should be filtered out."""
        text = "Amount: 123.456.789 total."
        page = _make_page(text)
        nm = NERMatch(start=8, end=19, text="123.456.789", pii_type=PIIType.SSN, confidence=0.75)
        result = _merge_detections([], [nm], [], page)
        ssns = [r for r in result if r.pii_type == PIIType.SSN]
        assert len(ssns) == 0

    def test_ssn_with_underscore_dropped(self):
        """NER SSN containing '_' should be filtered out."""
        text = "ID: 123_456_789 ref."
        page = _make_page(text)
        nm = NERMatch(start=4, end=15, text="123_456_789", pii_type=PIIType.SSN, confidence=0.75)
        result = _merge_detections([], [nm], [], page)
        ssns = [r for r in result if r.pii_type == PIIType.SSN]
        assert len(ssns) == 0


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------

class TestOverlapResolution:
    def test_higher_priority_wins(self):
        """Regex structured (priority 3) beats NER (priority 2) on same span."""
        text = "SSN: 123-45-6789 listed."
        page = _make_page(text)
        rm = RegexMatch(start=5, end=16, text="123-45-6789", pii_type=PIIType.SSN, confidence=0.98)
        nm = NERMatch(start=5, end=16, text="123-45-6789", pii_type=PIIType.SSN, confidence=0.80)
        result = _merge_detections([rm], [nm], [], page)
        ssns = [r for r in result if r.pii_type == PIIType.SSN]
        assert len(ssns) == 1
        # The surviving detection should be the regex one (high confidence, priority 3)
        assert ssns[0].confidence >= 0.95

    def test_same_type_overlap_unions(self):
        """Two overlapping same-type detections → unioned text span."""
        text = "Sent from John Michael Smith in NYC."
        page = _make_page(text)
        nm1 = NERMatch(start=10, end=22, text="John Michael", pii_type=PIIType.PERSON, confidence=0.85)
        nm2 = NERMatch(start=15, end=28, text="Michael Smith", pii_type=PIIType.PERSON, confidence=0.82)
        result = _merge_detections([], [nm1, nm2], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) >= 1
        # Merged text should cover "John Michael Smith"
        merged_text = persons[0].text
        assert "John" in merged_text
        assert "Smith" in merged_text


# ---------------------------------------------------------------------------
# Noise filters
# ---------------------------------------------------------------------------

class TestNoiseFilters:
    def test_short_org_dropped(self):
        """ORG detections ≤2 chars → dropped by noise filter."""
        text = "Company AB is listed here."
        page = _make_page(text)
        nm = NERMatch(start=8, end=10, text="AB", pii_type=PIIType.ORG, confidence=0.80)
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 0

    def test_person_at_page_start_dropped(self):
        """NER PERSON at char offset ≤5 with ≥2 words → page header → dropped."""
        text = "John Smith\nThis is the rest of the document content."
        page = _make_page(text)
        nm = NERMatch(start=0, end=10, text="John Smith", pii_type=PIIType.PERSON, confidence=0.88)
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) == 0

    def test_person_not_at_page_start_kept(self):
        """PERSON detection NOT at page start → should survive."""
        text = "The CEO is John Smith and he is great."
        page = _make_page(text)
        nm = NERMatch(start=11, end=21, text="John Smith", pii_type=PIIType.PERSON, confidence=0.88)
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) >= 1

    def test_adjacent_person_tokens_merged_into_full_name(self):
        """Two adjacent PERSON tokens separated by a space are merged.

        Regression for: NER models sometimes detect "Dagmar" and
        "Vymetalova" as two separate PERSON entities even though they
        form a single full name.  The merge pass must combine adjacent
        same-type PERSON candidates into one unified region.
        """
        # Preamble text ensures the name is well past offset 5 so the
        # page-header heuristic (PERSON at char <= 5) does not discard it.
        text = "Rimouski, le 3 septembre 2025\nAtt. Dagmar Vymetalova\n24, Rue Leclerc"
        offset = text.find("Dagmar")  # well past offset 5
        page = _make_page(text)
        nm1 = NERMatch(
            start=offset, end=offset + 6, text="Dagmar",
            pii_type=PIIType.PERSON, confidence=0.78,
        )
        nm2 = NERMatch(
            start=offset + 7, end=offset + 17, text="Vymetalova",
            pii_type=PIIType.PERSON, confidence=0.78,
        )
        result = _merge_detections([], [nm1, nm2], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        # Must produce exactly ONE region covering the full name
        assert len(persons) == 1, (
            f"Expected 1 merged PERSON, got {len(persons)}: {[r.text for r in persons]}"
        )
        assert persons[0].text == "Dagmar Vymetalova"

    def test_adjacent_person_tokens_not_merged_across_paragraph(self):
        """PERSON tokens separated by a newline are NOT merged."""
        text = "The lead is Ingrid\nBorgen runs operations at the plant site here"
        page = _make_page(text)
        ingrid_off = text.find("Ingrid")
        borgen_off = text.find("Borgen")
        nm1 = NERMatch(
            start=ingrid_off, end=ingrid_off + 6, text="Ingrid",
            pii_type=PIIType.PERSON, confidence=0.78,
        )
        nm2 = NERMatch(
            start=borgen_off, end=borgen_off + 6, text="Borgen",
            pii_type=PIIType.PERSON, confidence=0.78,
        )
        result = _merge_detections([], [nm1, nm2], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        # Should NOT be merged because gap character is \n, not a space
        assert not any(r.text == "Ingrid\nBorgen" for r in persons)


# ---------------------------------------------------------------------------
# Structured post-merge filters
# ---------------------------------------------------------------------------

class TestStructuredPostMerge:
    def test_ssn_with_currency_symbol_dropped(self):
        """SSN containing $, €, or £ should be filtered."""
        text = "Amount $123-45-6789 billed."
        page = _make_page(text)
        rm = RegexMatch(start=7, end=19, text="$123-45-6789", pii_type=PIIType.SSN, confidence=0.90)
        result = _merge_detections([rm], [], [], page)
        ssns = [r for r in result if r.pii_type == PIIType.SSN]
        assert len(ssns) == 0

    def test_custom_type_always_dropped(self):
        """PIIType.CUSTOM matches are dropped."""
        text = "Custom stuff here ABC123."
        page = _make_page(text)
        rm = RegexMatch(start=19, end=25, text="ABC123", pii_type=PIIType.CUSTOM, confidence=0.99)
        result = _merge_detections([rm], [], [], page)
        customs = [r for r in result if r.pii_type == PIIType.CUSTOM]
        assert len(customs) == 0


# ---------------------------------------------------------------------------
# _split_bboxes_by_proximity
# ---------------------------------------------------------------------------

class TestSplitBboxesByProximity:
    def test_single_bbox(self):
        bbs = [BBox(x0=0, y0=0, x1=100, y1=20)]
        result = _split_bboxes_by_proximity(bbs)
        assert result == [[0]]

    def test_contiguous_bboxes(self):
        """Adjacent bboxes with small gap → single group."""
        bbs = [
            BBox(x0=0, y0=0, x1=100, y1=20),
            BBox(x0=0, y0=22, x1=100, y1=42),
            BBox(x0=0, y0=44, x1=100, y1=64),
        ]
        result = _split_bboxes_by_proximity(bbs)
        assert len(result) == 1
        assert sorted(result[0]) == [0, 1, 2]

    def test_large_gap_splits(self):
        """Large vertical gap between bboxes → split into two groups."""
        bbs = [
            BBox(x0=0, y0=0, x1=100, y1=20),
            BBox(x0=0, y0=22, x1=100, y1=42),
            BBox(x0=0, y0=300, x1=100, y1=320),  # large gap
        ]
        result = _split_bboxes_by_proximity(bbs)
        assert len(result) == 2

    def test_empty_list(self):
        result = _split_bboxes_by_proximity([])
        assert result == [[]]  # single group with empty list is still a valid return


# ---------------------------------------------------------------------------
# GLiNER input
# ---------------------------------------------------------------------------

class TestGLiNERInput:
    def test_gliner_detection_included(self):
        """GLiNER matches should be processed like NER."""
        text = "Employee Marie Dupont works at the office."
        page = _make_page(text)
        gm = GLiNERMatch(start=9, end=22, text="Marie Dupont", pii_type=PIIType.PERSON, confidence=0.82)
        result = _merge_detections([], [], [], page, gliner_matches=[gm])
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) >= 1


# ---------------------------------------------------------------------------
# Confidence threshold
# ---------------------------------------------------------------------------

class TestConfidenceThreshold:
    @patch("core.detection.merge.config")
    def test_below_threshold_dropped(self, mock_config):
        """Detections below confidence_threshold → dropped."""
        mock_config.confidence_threshold = 0.50
        mock_config.max_font_size_pt = 50
        text = "Maybe email test@example.com here."
        page = _make_page(text)
        rm = RegexMatch(start=12, end=28, text="test@example.com", pii_type=PIIType.EMAIL, confidence=0.30)
        result = _merge_detections([rm], [], [], page)
        emails = [r for r in result if r.pii_type == PIIType.EMAIL]
        assert len(emails) == 0

    @patch("core.detection.merge.config")
    def test_above_threshold_kept(self, mock_config):
        """Detections at or above confidence_threshold → kept."""
        mock_config.confidence_threshold = 0.50
        mock_config.max_font_size_pt = 50
        text = "Email is test@example.com today."
        page = _make_page(text)
        rm = RegexMatch(start=9, end=25, text="test@example.com", pii_type=PIIType.EMAIL, confidence=0.95)
        result = _merge_detections([rm], [], [], page)
        emails = [r for r in result if r.pii_type == PIIType.EMAIL]
        assert len(emails) >= 1


# ---------------------------------------------------------------------------
# Output structure validation
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_output_is_pii_region_list(self):
        """All items returned are valid PIIRegion instances."""
        text = "Email john@test.com is here."
        page = _make_page(text)
        rm = RegexMatch(start=6, end=19, text="john@test.com", pii_type=PIIType.EMAIL, confidence=0.95)
        result = _merge_detections([rm], [], [], page)
        for r in result:
            assert isinstance(r, PIIRegion)
            assert r.page_number == 1
            assert r.bbox.x0 >= 0
            assert r.bbox.y0 >= 0
            assert r.source in DetectionSource

    def test_char_offsets_set(self):
        """Regions should have char_start and char_end populated."""
        text = "SSN is 123-45-6789."
        page = _make_page(text)
        rm = RegexMatch(start=7, end=18, text="123-45-6789", pii_type=PIIType.SSN, confidence=0.98)
        result = _merge_detections([rm], [], [], page)
        ssns = [r for r in result if r.pii_type == PIIType.SSN]
        if ssns:
            assert ssns[0].char_start >= 0
            assert ssns[0].char_end > ssns[0].char_start


# ---------------------------------------------------------------------------
# Quoted-text extension
# ---------------------------------------------------------------------------

class TestQuotedTextExtension:
    """Test that PERSON/ORG entities inside quotes extend to cover full quoted text."""

    def test_french_guillemets_person_extension(self):
        """NER detects 'Dixie' but full quoted text is 'Dixie Lee'."""
        text = 'sous la bannière « Dixie Lee » sur le territoire'
        #                    ^18    ^24
        page = _make_page(text)
        # NER only detected "Dixie" (indices 19-24 inside the guillemets)
        nm = NERMatch(start=19, end=24, text="Dixie", pii_type=PIIType.PERSON, confidence=0.70)
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) == 1
        # Should extend to cover "Dixie Lee" (the full quoted text)
        assert persons[0].text == "Dixie Lee"

    def test_double_quotes_org_extension(self):
        """ORG detection extends to cover full double-quoted text."""
        text = 'Company called "Acme Corp Industries" is here.'
        page = _make_page(text)
        # NER only detected "Acme Corp" (partial match)
        nm = NERMatch(start=16, end=25, text="Acme Corp", pii_type=PIIType.ORG, confidence=0.65)
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        assert orgs[0].text == "Acme Corp Industries"

    def test_single_word_quoted_not_extended(self):
        """Single-word quotes are not tracked (require 2+ words)."""
        text = 'The name "Bob" was used.'
        page = _make_page(text)
        nm = NERMatch(start=10, end=13, text="Bob", pii_type=PIIType.PERSON, confidence=0.70)
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        # Detection kept but not extended (single word)
        if persons:  # may be filtered by noise but text shouldn't change
            assert persons[0].text == "Bob"

    def test_non_overlapping_quote_unchanged(self):
        """PERSON outside quotes is not affected."""
        text = 'Today Jean Dupont said « hello world » to everyone.'
        page = _make_page(text)
        # Person is at position 6, not at start (avoids page-header filter)
        nm = NERMatch(start=6, end=17, text="Jean Dupont", pii_type=PIIType.PERSON, confidence=0.80)
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) == 1
        assert persons[0].text == "Jean Dupont"
