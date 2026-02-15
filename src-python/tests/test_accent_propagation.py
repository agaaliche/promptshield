"""Tests for accent-agnostic propagation.

Ensures that both ``propagate_regions_across_pages`` and
``propagate_partial_org_names`` match text regardless of diacritics,
so "Société" matches "Societe" and vice-versa.
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
    _strip_accents,
    propagate_regions_across_pages,
    propagate_partial_org_names,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(text: str, page_number: int = 1) -> PageData:
    """Build a PageData with per-line text blocks so bboxes are distinct."""
    lines = text.split("\n") if "\n" in text else [text]
    if len(lines) == 1 and ". " in text:
        parts = text.split(". ")
        lines = [p + "." if i < len(parts) - 1 else p for i, p in enumerate(parts)]
    blocks: list[TextBlock] = []
    y = 50.0
    for i, line in enumerate(lines):
        blocks.append(TextBlock(
            text=line,
            bbox=BBox(x0=50, y0=y, x1=550, y1=y + 15),
            block_index=i,
            line_index=i,
            word_index=0,
        ))
        y += 20
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
# Tests for _strip_accents
# ---------------------------------------------------------------------------

class TestStripAccents:
    def test_basic_accents(self):
        assert _strip_accents("é") == "e"
        assert _strip_accents("ü") == "u"
        assert _strip_accents("ñ") == "n"
        assert _strip_accents("ö") == "o"
        assert _strip_accents("ç") == "c"

    def test_preserves_length(self):
        text = "Société Générale"
        result = _strip_accents(text)
        assert len(result) == len(text)
        assert result == "Societe Generale"

    def test_no_accents_unchanged(self):
        text = "Hello World"
        assert _strip_accents(text) == text

    def test_mixed(self):
        assert _strip_accents("naïve café") == "naive cafe"

    def test_german(self):
        assert _strip_accents("für über") == "fur uber"

    def test_empty_string(self):
        assert _strip_accents("") == ""


# ---------------------------------------------------------------------------
# Tests for accent-agnostic exact propagation
# ---------------------------------------------------------------------------

class TestAccentExactPropagation:
    """propagate_regions_across_pages should match accented ↔ unaccented."""

    def test_accented_template_finds_unaccented_text(self):
        """Detected "Société Générale" on page 1 → find "Societe Generale" on page 2."""
        text1 = "Document about Société Générale here."
        text2 = "Also Societe Generale mentioned. Plus something else."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("Société Générale")
        region = _make_region("Société Générale", char_start=idx, page_number=1)

        result = propagate_regions_across_pages([region], [page1, page2])

        # Should find it on page 2
        page2_regions = [r for r in result if r.page_number == 2]
        assert len(page2_regions) >= 1
        texts = [r.text for r in page2_regions]
        assert "Societe Generale" in texts

    def test_unaccented_template_finds_accented_text(self):
        """Detected "Societe Generale" on page 1 → find "Société Générale" on page 2."""
        text1 = "Document about Societe Generale here."
        text2 = "Also Société Générale mentioned. Plus something extra."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("Societe Generale")
        region = _make_region("Societe Generale", char_start=idx, page_number=1)

        result = propagate_regions_across_pages([region], [page1, page2])

        page2_regions = [r for r in result if r.page_number == 2]
        assert len(page2_regions) >= 1
        texts = [r.text for r in page2_regions]
        assert "Société Générale" in texts

    def test_person_accent_agnostic(self):
        """Accent-agnostic works for PERSON type too, not just ORG."""
        text1 = "Signed by José García today."
        text2 = "Review by Jose Garcia next week. Other content follows."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("José García")
        region = _make_region("José García", pii_type=PIIType.PERSON,
                              char_start=idx, page_number=1)

        result = propagate_regions_across_pages([region], [page1, page2])

        page2_regions = [r for r in result if r.page_number == 2]
        assert len(page2_regions) >= 1
        texts = [r.text for r in page2_regions]
        assert "Jose Garcia" in texts
        # Type preserved
        assert all(r.pii_type == PIIType.PERSON for r in page2_regions)

    def test_german_umlauts(self):
        """Müller ↔ Muller."""
        text1 = "Contact Herr Müller for details."
        text2 = "Herr Muller confirmed the order. End of page."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("Herr Müller")
        region = _make_region("Herr Müller", pii_type=PIIType.PERSON,
                              char_start=idx, page_number=1)

        result = propagate_regions_across_pages([region], [page1, page2])

        page2_regions = [r for r in result if r.page_number == 2]
        assert any(r.text == "Herr Muller" for r in page2_regions)

    def test_same_page_accent_variant(self):
        """Both variants on same page — both found."""
        text = "Société Générale est grande. Societe Generale aussi."
        page = _make_page(text, page_number=1)

        idx = text.find("Société Générale")
        region = _make_region("Société Générale", char_start=idx, page_number=1)

        result = propagate_regions_across_pages([region], [page])

        texts = [r.text for r in result]
        assert "Société Générale" in texts
        assert "Societe Generale" in texts

    def test_accent_merge_dedup(self):
        """Two accent variants of the same word merge into one template (higher confidence wins)."""
        text1 = "About Société Générale here."
        text2 = "About Societe Generale here. And more content."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx1 = text1.find("Société Générale")
        r1 = _make_region("Société Générale", char_start=idx1, page_number=1,
                           confidence=0.90)
        idx2 = text2.find("Societe Generale")
        r2 = _make_region("Societe Generale", char_start=idx2, page_number=2,
                           confidence=0.70)

        result = propagate_regions_across_pages([r1, r2], [page1, page2])

        # Both pages should have regions; higher-confidence template wins
        assert any(r.page_number == 1 for r in result)
        assert any(r.page_number == 2 for r in result)


# ---------------------------------------------------------------------------
# Tests for accent-agnostic partial ORG propagation
# ---------------------------------------------------------------------------

class TestAccentPartialOrgPropagation:
    """propagate_partial_org_names should match sub-phrases accent-agnostically."""

    def test_accented_org_unaccented_subphrase(self):
        """Detected "Société Générale France" → find "Societe Generale" in text."""
        text = "Société Générale France is big. Societe Generale matters."
        page = _make_page(text, page_number=1)

        idx = text.find("Société Générale France")
        region = _make_region("Société Générale France", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        all_texts = [r.text for r in result]
        assert "Societe Generale" in all_texts

    def test_unaccented_org_accented_subphrase(self):
        """Detected "Societe Generale France" → find "Société Générale" in text."""
        text = "Societe Generale France is big. Société Générale matters."
        page = _make_page(text, page_number=1)

        idx = text.find("Societe Generale France")
        region = _make_region("Societe Generale France", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        all_texts = [r.text for r in result]
        assert "Société Générale" in all_texts

    def test_partial_org_cross_page_accent(self):
        """ORG on page 1 with accents, sub-phrase on page 2 without."""
        text1 = "Contract with Société Générale France signed."
        text2 = "Societe Generale confirmed. Other info follows."
        page1 = _make_page(text1, page_number=1)
        page2 = _make_page(text2, page_number=2)

        idx = text1.find("Société Générale France")
        region = _make_region("Société Générale France", char_start=idx, page_number=1)

        result = propagate_partial_org_names([region], [page1, page2])

        page2_regions = [r for r in result if r.page_number == 2]
        assert any("Societe Generale" in r.text for r in page2_regions)

    def test_function_word_accent_filter(self):
        """Function words with accents (für, über) should still be filtered."""
        # "für über" are function words; a sub-phrase of only function words
        # should be skipped even when accents differ
        text = "Test für über GmbH entity. fur uber appears."
        page = _make_page(text, page_number=1)

        idx = text.find("für über GmbH")
        # Note: this is contrived — real ORGs wouldn't look like this,
        # but we're testing the function-word filter
        region = _make_region("für über GmbH", char_start=idx)

        result = propagate_partial_org_names([region], [page])

        # "für über" (2 function words only) should NOT be propagated
        all_texts = [r.text for r in result if r.id != region.id]
        # No sub-phrase of only function words should appear
        for t in all_texts:
            assert t.lower().strip() not in {"für über", "fur uber"}
