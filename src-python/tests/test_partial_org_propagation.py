"""Tests for partial ORG name propagation.

When a multi-word ORG name like "Deutsche Bank AG" is detected, any
2+-word contiguous subset (e.g. "Deutsche Bank") that appears in the
text should also be flagged as an ORG region.
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
from core.detection.propagation import (
    _generate_contiguous_subphrases,
    propagate_partial_org_names,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(text: str, page_number: int = 1) -> PageData:
    """Build a PageData with per-line text blocks so bboxes are distinct."""
    lines = text.split("\n") if "\n" in text else [text]
    # If single-line, try splitting on ". " to get distinct blocks
    if len(lines) == 1 and ". " in text:
        # Split into sentence-sized blocks at ". " boundaries
        parts = text.split(". ")
        lines = [p + "." if i < len(parts) - 1 else p for i, p in enumerate(parts)]
    blocks: list[TextBlock] = []
    y = 50.0
    offset = 0
    for i, line in enumerate(lines):
        blocks.append(TextBlock(
            text=line,
            bbox=BBox(x0=50, y0=y, x1=550, y1=y + 15),
            block_index=i,
            line_index=i,
            word_index=0,
        ))
        y += 20
        offset += len(line)
    return PageData(
        page_number=page_number,
        width=612,
        height=792,
        bitmap_path="/tmp/page.png",
        text_blocks=blocks,
        full_text=text,
    )


def _make_region(
    text: str,
    pii_type: PIIType = PIIType.ORG,
    page_number: int = 1,
    confidence: float = 0.80,
    char_start: int = 0,
    char_end: int | None = None,
) -> PIIRegion:
    if char_end is None:
        char_end = char_start + len(text)
    return PIIRegion(
        id="aabbccddee01",
        page_number=page_number,
        bbox=BBox(x0=50, y0=50, x1=200, y1=70),
        text=text,
        pii_type=pii_type,
        confidence=confidence,
        source=DetectionSource.NER,
        char_start=char_start,
        char_end=char_end,
    )


# ---------------------------------------------------------------------------
# Tests for _generate_contiguous_subphrases
# ---------------------------------------------------------------------------

class TestGenerateSubphrases:
    def test_three_words(self):
        result = _generate_contiguous_subphrases(["A", "B", "C"])
        assert result == ["A B", "B C"]

    def test_four_words(self):
        result = _generate_contiguous_subphrases(["A", "B", "C", "D"])
        # 2-word: A B, B C, C D   3-word: A B C, B C D
        assert "A B" in result
        assert "B C" in result
        assert "C D" in result
        assert "A B C" in result
        assert "B C D" in result
        # Full phrase excluded
        assert "A B C D" not in result

    def test_two_words_no_output(self):
        """Two-word input has no sub-phrases (min_words=2 would be the full phrase)."""
        result = _generate_contiguous_subphrases(["A", "B"])
        assert result == []

    def test_five_words(self):
        result = _generate_contiguous_subphrases(["A", "B", "C", "D", "E"])
        assert len(result) == 4 + 3 + 2  # 2-word(4), 3-word(3), 4-word(2) = 9


# ---------------------------------------------------------------------------
# Tests for propagate_partial_org_names
# ---------------------------------------------------------------------------

class TestPartialOrgPropagation:
    """Core behaviour: sub-phrases of detected ORGs are flagged."""

    def test_basic_sub_phrase_detected(self):
        """'Deutsche Bank' should be flagged when 'Deutsche Bank AG' is known."""
        text = "The Deutsche Bank AG is large. Contact Deutsche Bank for info."
        page = _make_page(text)
        idx = text.find("Deutsche Bank AG")
        region = _make_region("Deutsche Bank AG", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        # Should have the original + new region for "Deutsche Bank"
        texts = [r.text for r in result]
        assert "Deutsche Bank AG" in texts
        assert "Deutsche Bank" in texts

    def test_sub_phrase_confidence_reduced(self):
        """Sub-phrase regions get 85% of the parent confidence."""
        text = "Acme International Corp pays well. Acme International is great."
        page = _make_page(text)
        idx = text.find("Acme International Corp")
        region = _make_region("Acme International Corp", confidence=0.80, char_start=idx)

        result = propagate_partial_org_names([region], [page])

        sub_regions = [r for r in result if r.text == "Acme International"]
        assert len(sub_regions) >= 1
        assert sub_regions[0].confidence == pytest.approx(0.80 * 0.85, abs=0.01)

    def test_no_propagation_for_two_word_org(self):
        """ORGs with only 2 words should NOT produce sub-phrases (min 3 words)."""
        text = "Acme Corp is here. Acme is everywhere."
        page = _make_page(text)
        idx = text.find("Acme Corp")
        region = _make_region("Acme Corp", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        # Only the original — no sub-phrases generated from 2-word ORG
        assert len(result) == 1
        assert result[0].text == "Acme Corp"

    def test_no_duplicate_if_already_detected(self):
        """If a sub-phrase is already a detected region, don't duplicate it."""
        text = "Deutsche Bank AG is here. Deutsche Bank also appears."
        page = _make_page(text)
        idx1 = text.find("Deutsche Bank AG")
        idx2 = text.find("Deutsche Bank also") 
        r1 = _make_region("Deutsche Bank AG", char_start=idx1)
        # Simulate that "Deutsche Bank" was already detected at idx2
        r2 = _make_region("Deutsche Bank", char_start=idx2, char_end=idx2 + len("Deutsche Bank"))

        result = propagate_partial_org_names([r1, r2], [page])

        # "Deutsche Bank" at idx2 already exists, no new region there
        db_regions = [r for r in result if r.text == "Deutsche Bank"]
        assert len(db_regions) == 1  # only the one that was already there

    def test_word_boundary_respected(self):
        """Should NOT match sub-phrases inside other words."""
        # "BankAG" should not match "Bank" sub-phrase since no word boundary
        text = "Foo Bar Baz Inc is nice. FooBar should not match."
        page = _make_page(text)
        idx = text.find("Foo Bar Baz Inc")
        region = _make_region("Foo Bar Baz Inc", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        # "FooBar" should NOT be flagged (no word boundary between Foo and Bar)
        for r in result:
            if r.text == "Foo Bar":
                # Should not start inside "FooBar"
                assert r.char_start != text.find("FooBar")

    def test_cross_page_propagation(self):
        """Sub-phrases found on other pages are also flagged."""
        text1 = "Contract with Siemens Healthineers AG."
        text2 = "Siemens Healthineers will provide services."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("Siemens Healthineers AG")
        region = _make_region("Siemens Healthineers AG", page_number=1, char_start=idx)

        result = propagate_partial_org_names([region], [page1, page2])

        page2_regions = [r for r in result if r.page_number == 2]
        page2_texts = [r.text for r in page2_regions]
        assert "Siemens Healthineers" in page2_texts

    def test_noise_sub_phrases_filtered(self):
        """Sub-phrases made entirely of function words should be filtered out."""
        # Construct an ORG where a sub-phrase is purely function words
        text = "Société Des Et Ltd signed. Des Et appears here."
        page = _make_page(text)
        idx = text.find("Société Des Et Ltd")
        region = _make_region("Société Des Et Ltd", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        texts = [r.text for r in result]
        # "Des Et" is purely function words → should be filtered
        assert "Des Et" not in texts

    def test_non_org_regions_unchanged(self):
        """Non-ORG regions should pass through untouched."""
        text = "John Smith works at Acme International Corp."
        page = _make_page(text)
        idx_person = text.find("John Smith")
        idx_org = text.find("Acme International Corp")
        r_person = _make_region("John Smith", pii_type=PIIType.PERSON, char_start=idx_person)
        r_org = _make_region("Acme International Corp", char_start=idx_org)

        result = propagate_partial_org_names([r_person, r_org], [page])

        person_regions = [r for r in result if r.pii_type == PIIType.PERSON]
        assert len(person_regions) == 1
        assert person_regions[0].text == "John Smith"

    def test_empty_input(self):
        """Empty regions or pages returns empty."""
        assert propagate_partial_org_names([], []) == []

    def test_legal_suffix_sub_phrase_survives(self):
        """Sub-phrases containing a legal suffix should survive."""
        text = "Munich Reinsurance Company AG is big. Reinsurance Company AG was mentioned."
        page = _make_page(text)
        idx = text.find("Munich Reinsurance Company AG")
        region = _make_region("Munich Reinsurance Company AG", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        texts = [r.text for r in result]
        # Longer sub-phrase "Reinsurance Company AG" should match (processed first)
        assert "Reinsurance Company AG" in texts

    def test_multiple_orgs_produce_sub_phrases(self):
        """Multiple detected ORGs each produce their own sub-phrases."""
        text = (
            "Signed by Goldman Sachs Group Inc and JPMorgan Chase Bank. "
            "Goldman Sachs will handle payments. JPMorgan Chase agrees."
        )
        page = _make_page(text)
        idx1 = text.find("Goldman Sachs Group Inc")
        idx2 = text.find("JPMorgan Chase Bank")
        r1 = _make_region("Goldman Sachs Group Inc", char_start=idx1)
        r2 = _make_region("JPMorgan Chase Bank", char_start=idx2)

        result = propagate_partial_org_names([r1, r2], [page])
        texts = [r.text for r in result]

        assert "Goldman Sachs" in texts
        assert "JPMorgan Chase" in texts

    def test_region_type_is_org(self):
        """All propagated sub-phrase regions have PIIType.ORG."""
        text = "Acme International Corp pays well. Acme International is great."
        page = _make_page(text)
        idx = text.find("Acme International Corp")
        region = _make_region("Acme International Corp", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        for r in result:
            if r.text == "Acme International":
                assert r.pii_type == PIIType.ORG
