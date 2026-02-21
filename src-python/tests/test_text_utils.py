"""Tests for core.text_utils — accent stripping, ws_collapse, normalize_for_matching."""

from __future__ import annotations

import pytest

from core.text_utils import (
    strip_accents,
    remove_accents,
    ws_collapse,
    normalize_for_matching,
)


# ---------------------------------------------------------------------------
# strip_accents
# ---------------------------------------------------------------------------

class TestStripAccents:
    def test_plain_ascii_unchanged(self):
        assert strip_accents("Hello World") == "Hello World"

    def test_length_preserved(self):
        text = "éàüöñç"
        result = strip_accents(text)
        assert len(result) == len(text)

    def test_basic_accents(self):
        assert strip_accents("é") == "e"
        assert strip_accents("à") == "a"
        assert strip_accents("ü") == "u"
        assert strip_accents("ö") == "o"
        assert strip_accents("ñ") == "n"
        assert strip_accents("ç") == "c"

    def test_ligatures(self):
        assert strip_accents("ß") == "s"
        assert strip_accents("æ") == "a"
        assert strip_accents("œ") == "o"
        assert strip_accents("ø") == "o"
        assert strip_accents("ł") == "l"

    def test_capital_ligatures(self):
        assert strip_accents("Æ") == "A"
        assert strip_accents("Œ") == "O"
        assert strip_accents("Ø") == "O"
        assert strip_accents("Ł") == "L"

    def test_empty_string(self):
        assert strip_accents("") == ""

    def test_mixed_sentence(self):
        result = strip_accents("Société MARTIN & Frères")
        assert result == "Societe MARTIN & Freres"

    def test_german_umlauts(self):
        assert strip_accents("Müller") == "Muller"
        assert strip_accents("Ärger") == "Arger"

    def test_length_preserved_on_sentence(self):
        text = "Héloïse était là"
        assert len(strip_accents(text)) == len(text)


# ---------------------------------------------------------------------------
# remove_accents
# ---------------------------------------------------------------------------

class TestRemoveAccents:
    def test_basic(self):
        assert remove_accents("éàü") == "eau"

    def test_ascii_unchanged(self):
        assert remove_accents("ABC123") == "ABC123"

    def test_empty(self):
        assert remove_accents("") == ""


# ---------------------------------------------------------------------------
# ws_collapse
# ---------------------------------------------------------------------------

class TestWsCollapse:
    def test_single_spaces_unchanged(self):
        assert ws_collapse("a b c") == "a b c"

    def test_multiple_spaces_collapsed(self):
        assert ws_collapse("a   b") == "a b"

    def test_tabs_collapsed(self):
        assert ws_collapse("a\tb") == "a b"

    def test_newlines_collapsed(self):
        assert ws_collapse("a\nb") == "a b"

    def test_mixed_whitespace(self):
        assert ws_collapse("a  \t\n  b") == "a b"

    def test_leading_trailing_stripped(self):
        assert ws_collapse("  hello  ") == "hello"

    def test_empty(self):
        assert ws_collapse("") == ""

    def test_only_whitespace(self):
        assert ws_collapse("   ") == ""


# ---------------------------------------------------------------------------
# normalize_for_matching
# ---------------------------------------------------------------------------

class TestNormalizeForMatching:
    def test_lowercases(self):
        assert normalize_for_matching("HELLO") == "hello"

    def test_strips_accents(self):
        assert normalize_for_matching("Société") == "societe"

    def test_collapses_whitespace(self):
        assert normalize_for_matching("A   B") == "a b"

    def test_normalises_curly_apostrophe(self):
        # RIGHT SINGLE QUOTATION MARK U+2019 → ASCII apostrophe
        result = normalize_for_matching("L\u2019Esprit")
        assert result == normalize_for_matching("L'Esprit")

    def test_normalises_left_single_quote(self):
        result = normalize_for_matching("L\u2018Esprit")
        assert result == normalize_for_matching("L'Esprit")

    def test_normalises_en_dash(self):
        # EN DASH U+2013 → hyphen
        result = normalize_for_matching("JACQUES\u2013CARTIER")
        assert result == "jacques-cartier"

    def test_normalises_em_dash(self):
        result = normalize_for_matching("fin\u2014de")
        assert result == "fin-de"

    def test_accented_equals_unaccented_after_normalize(self):
        assert normalize_for_matching("Société") == normalize_for_matching("Societe")

    def test_curly_quote_equals_straight_apostrophe(self):
        assert normalize_for_matching("L\u2019Esprit") == normalize_for_matching("L'Esprit")

    def test_empty(self):
        assert normalize_for_matching("") == ""

    def test_preserves_digits(self):
        assert normalize_for_matching("ABC 123") == "abc 123"
