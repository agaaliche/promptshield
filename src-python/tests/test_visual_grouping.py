"""Tests for visual-grouping ORG confidence boost in core.detection.merge.

Covers:
  - Quoted-text boost (double, single, curly quotes, guillemets)
  - Bold / italic font boost
  - Horizontally-centred text boost
  - No boost for single-word ORGs
  - No boost for non-ORG types
  - No double-boost (only first matching heuristic applies)
"""

from __future__ import annotations

import pytest

from models.schemas import (
    BBox,
    DetectionSource,
    PIIRegion,
    PIIType,
    PageData,
    TextBlock,
)
from core.detection.ner_detector import NERMatch
from core.detection.regex_detector import RegexMatch
from core.detection.merge import _merge_detections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page_blocks(
    text: str,
    blocks: list[TextBlock],
    width: float = 612,
    height: float = 792,
) -> PageData:
    """Build a PageData with explicit text blocks."""
    return PageData(
        page_number=1,
        width=width,
        height=height,
        bitmap_path="/tmp/page.png",
        text_blocks=blocks,
        full_text=text,
    )


def _word_blocks(
    text: str,
    *,
    x0: float = 50,
    y0: float = 50,
    x1: float = 550,
    y1: float = 70,
    is_bold: bool = False,
    is_italic: bool = False,
) -> list[TextBlock]:
    """Split *text* into one TextBlock per word, distributing x across [x0, x1]."""
    words = text.split()
    if not words:
        return []
    w = (x1 - x0) / len(words)
    blocks: list[TextBlock] = []
    offset = 0
    for i, word in enumerate(words):
        blocks.append(TextBlock(
            text=word,
            bbox=BBox(x0=x0 + i * w, y0=y0, x1=x0 + (i + 1) * w, y1=y1),
            block_index=0,
            line_index=0,
            word_index=i,
            is_bold=is_bold,
            is_italic=is_italic,
        ))
        offset += len(word) + 1  # +1 for space
    return blocks


# ---------------------------------------------------------------------------
# 1. Quoted-text boost
# ---------------------------------------------------------------------------

class TestQuotedTextBoost:
    """ORG candidates enclosed in quotation marks should receive a boost."""

    @pytest.mark.parametrize("qopen,qclose", [
        ('"', '"'),
        ("'", "'"),
        ('\u201c', '\u201d'),  # curly double quotes
        ('\u2018', '\u2019'),  # curly single quotes
        ('\u00ab', '\u00bb'),  # guillemets
    ])
    def test_quoted_org_gets_boost(self, qopen: str, qclose: str):
        org_name = "Acme Corp"
        text = f"Contact {qopen}{org_name}{qclose} for details."
        blocks = _word_blocks(text)
        page = _make_page_blocks(text, blocks)

        start = text.index(org_name)
        end = start + len(org_name)
        nm = NERMatch(
            start=start, end=end, text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        # 0.60 + 0.12 = 0.72
        assert orgs[0].confidence >= 0.71

    def test_unquoted_org_no_quote_boost(self):
        text = "Contact Acme Corp for details."
        blocks = _word_blocks(text)
        page = _make_page_blocks(text, blocks)

        start = text.index("Acme Corp")
        end = start + len("Acme Corp")
        nm = NERMatch(
            start=start, end=end, text="Acme Corp",
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        # Should still appear but without the +0.12 boost
        assert len(orgs) == 1
        assert orgs[0].confidence < 0.71

    def test_single_word_in_quotes_no_boost(self):
        """Single-word ORGs are not boosted even if quoted."""
        text = 'Contact "Acme" for details.'
        blocks = _word_blocks(text)
        page = _make_page_blocks(text, blocks)

        # The org candidate is just "Acme" (1 word)
        start = text.index("Acme")
        end = start + len("Acme")
        nm = NERMatch(
            start=start, end=end, text="Acme",
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        # May or may not survive noise filters, but if it does, no boost
        for o in orgs:
            assert o.confidence <= 0.61  # essentially same as input


# ---------------------------------------------------------------------------
# 2. Bold / italic boost
# ---------------------------------------------------------------------------

class TestBoldItalicBoost:
    """ORG candidates rendered in bold or italic should be boosted."""

    def test_bold_org_gets_boost(self):
        org_name = "Nextera Corp"
        text = f"Working at {org_name} is great."
        # Build blocks: the ORG words are bold, rest are not
        blocks: list[TextBlock] = []
        words = text.split()
        w = 500 / len(words)
        for i, word in enumerate(words):
            bold = word in ("Nextera", "Corp")
            blocks.append(TextBlock(
                text=word,
                bbox=BBox(x0=50 + i * w, y0=50, x1=50 + (i + 1) * w, y1=70),
                block_index=0, line_index=0, word_index=i,
                is_bold=bold, is_italic=False,
            ))
        page = _make_page_blocks(text, blocks)

        start = text.index(org_name)
        end = start + len(org_name)
        nm = NERMatch(
            start=start, end=end, text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        assert orgs[0].confidence >= 0.71

    def test_italic_org_gets_boost(self):
        org_name = "Zylox Dynamics"
        text = f"Visit {org_name} today."
        blocks: list[TextBlock] = []
        words = text.split()
        w = 500 / len(words)
        for i, word in enumerate(words):
            italic = word in ("Zylox", "Dynamics")
            blocks.append(TextBlock(
                text=word,
                bbox=BBox(x0=50 + i * w, y0=50, x1=50 + (i + 1) * w, y1=70),
                block_index=0, line_index=0, word_index=i,
                is_bold=False, is_italic=italic,
            ))
        page = _make_page_blocks(text, blocks)

        start = text.index(org_name)
        end = start + len(org_name)
        nm = NERMatch(
            start=start, end=end, text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        assert orgs[0].confidence >= 0.71

    def test_non_bold_org_no_style_boost(self):
        org_name = "Plain Corp"
        text = f"At {org_name} we work."
        blocks = _word_blocks(text, is_bold=False, is_italic=False)
        page = _make_page_blocks(text, blocks)

        start = text.index(org_name)
        end = start + len(org_name)
        nm = NERMatch(
            start=start, end=end, text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        assert orgs[0].confidence < 0.71


# ---------------------------------------------------------------------------
# 3. Horizontally-centred boost
# ---------------------------------------------------------------------------

class TestCentredBoost:
    """ORG candidates with >12% blank margin on each side get boosted."""

    def test_centred_org_gets_boost(self):
        org_name = "Central Corp"
        text = org_name  # the full text is just the org name
        # Centred: x0 at ~25% of 612, x1 at ~75% — margins ~25% each
        blocks = _word_blocks(
            text,
            x0=150, y0=50, x1=460, y1=70,
        )
        page = _make_page_blocks(text, blocks, width=612)

        nm = NERMatch(
            start=0, end=len(org_name), text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        assert orgs[0].confidence >= 0.71

    def test_left_aligned_org_no_centre_boost(self):
        org_name = "Left Corp"
        text = org_name
        # Left-aligned: x0 near 0, so left_margin < 12%
        blocks = _word_blocks(
            text,
            x0=10, y0=50, x1=300, y1=70,
        )
        page = _make_page_blocks(text, blocks, width=612)

        nm = NERMatch(
            start=0, end=len(org_name), text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        # Should not get a boost
        for o in orgs:
            assert o.confidence < 0.71


# ---------------------------------------------------------------------------
# 4. Non-ORG types should NOT be boosted
# ---------------------------------------------------------------------------

class TestNonOrgNoBoost:
    """Visual-grouping boost is ORG-only; other types are unaffected."""

    def test_person_in_quotes_no_boost(self):
        text = 'Call "John Smith" for info.'
        blocks = _word_blocks(text)
        page = _make_page_blocks(text, blocks)

        start = text.index("John Smith")
        end = start + len("John Smith")
        nm = NERMatch(
            start=start, end=end, text="John Smith",
            pii_type=PIIType.PERSON, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) == 1
        # Should NOT get the visual boost
        assert persons[0].confidence < 0.71

    def test_bold_person_no_boost(self):
        # Place the PERSON at char offset > 5 to avoid page-header filter
        text = "Please meet John Smith today."
        blocks: list[TextBlock] = []
        words = text.split()
        w = 500 / len(words)
        for i, word in enumerate(words):
            bold = word in ("John", "Smith")
            blocks.append(TextBlock(
                text=word,
                bbox=BBox(x0=50 + i * w, y0=50, x1=50 + (i + 1) * w, y1=70),
                block_index=0, line_index=0, word_index=i,
                is_bold=bold,
            ))
        page = _make_page_blocks(text, blocks)

        start = text.index("John Smith")
        end = start + len("John Smith")
        nm = NERMatch(
            start=start, end=end, text="John Smith",
            pii_type=PIIType.PERSON, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        persons = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(persons) == 1
        assert persons[0].confidence < 0.71


# ---------------------------------------------------------------------------
# 5. No double-boost — only first heuristic fires
# ---------------------------------------------------------------------------

class TestNoDoubleboost:
    """A candidate matching multiple heuristics should only be boosted once."""

    def test_quoted_and_bold_gets_single_boost(self):
        org_name = "Super Corp"
        text = f'Contact "{org_name}" today.'
        # Build blocks — the ORG words are also bold
        blocks: list[TextBlock] = []
        words = text.split()
        w = 500 / len(words)
        for i, word in enumerate(words):
            raw = word.strip('"')
            bold = raw in ("Super", "Corp")
            blocks.append(TextBlock(
                text=word,
                bbox=BBox(x0=50 + i * w, y0=50, x1=50 + (i + 1) * w, y1=70),
                block_index=0, line_index=0, word_index=i,
                is_bold=bold,
            ))
        page = _make_page_blocks(text, blocks)

        start = text.index(org_name)
        end = start + len(org_name)
        nm = NERMatch(
            start=start, end=end, text=org_name,
            pii_type=PIIType.ORG, confidence=0.60,
        )
        result = _merge_detections([], [nm], [], page)
        orgs = [r for r in result if r.pii_type == PIIType.ORG]
        assert len(orgs) == 1
        # Should be exactly one +0.15 boost, not two (0.60 + 0.15 = 0.75)
        assert 0.74 <= orgs[0].confidence <= 0.76
