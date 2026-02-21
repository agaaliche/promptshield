"""Tests for the noise filtering module."""

import pytest

from core.detection.noise_filters import (
    has_legal_suffix,
    _is_org_pipeline_noise,
    _is_loc_pipeline_noise,
    _is_german_compound_noun,
    _is_person_pipeline_noise,
    _is_address_number_only,
    _strip_phone_labels_from_address,
)


# ── has_legal_suffix ─────────────────────────────────────────────────────

class TestLegalSuffix:
    @pytest.mark.parametrize("text", [
        "Acme Inc", "Acme Inc.", "Globex Corp", "Foo Ltd", "Bar LLC",
        "Baz GmbH", "Qux AG", "Corge S.A.", "Grault SRL", "Garply BV",
        "Waldo SE", "Fred SARL", "Plugh KG",
    ])
    def test_detects_legal_suffix(self, text: str):
        assert has_legal_suffix(text) is True

    @pytest.mark.parametrize("text", [
        "Department of Education", "Central Park", "some random words",
        "International", "Hello World",
    ])
    def test_no_legal_suffix(self, text: str):
        assert has_legal_suffix(text) is False


# ── ORG noise filter ─────────────────────────────────────────────────────

class TestOrgNoise:
    def test_common_words_are_noise(self):
        """Generic dictionary words without a legal suffix → noise."""
        assert _is_org_pipeline_noise("International") is True
        assert _is_org_pipeline_noise("the department") is True

    def test_real_org_with_suffix_not_noise(self):
        """A name with a legal suffix should NOT be filtered."""
        assert _is_org_pipeline_noise("Acme Inc.") is False

    def test_short_string_is_noise(self):
        """Very short strings are treated as noise."""
        assert _is_org_pipeline_noise("A") is True
        assert _is_org_pipeline_noise("") is True


# ── PERSON noise filter ──────────────────────────────────────────────────

class TestPersonNoise:
    def test_empty_or_short(self):
        assert _is_person_pipeline_noise("") is True
        assert _is_person_pipeline_noise("A") is True
        assert _is_person_pipeline_noise("Mr") is True

    def test_digit_prefix_is_noise(self):
        assert _is_person_pipeline_noise("1st Battalion") is True

    def test_pure_digits_is_noise(self):
        assert _is_person_pipeline_noise("12345") is True

    def test_initials_are_noise(self):
        assert _is_person_pipeline_noise("A.B.C") is True
        assert _is_person_pipeline_noise("J.K") is True

    def test_single_uppercase_word_is_noise(self):
        assert _is_person_pipeline_noise("DEPARTMENT") is True

    def test_real_name_not_noise(self):
        assert _is_person_pipeline_noise("John Smith") is False

    def test_single_firstname_not_noise(self):
        """Single capital first names must NOT be filtered.

        Regression for: word-frequency dictionaries include common first names
        (Robert, Stefan, Dagmar…), which caused _is_single_word_dict_noise to
        falsely flag them as common nouns and drop them from NER detections.
        """
        for name in ["Dagmar", "Stefan", "Robert", "Viktor", "Kaspar", "Alfred"]:
            assert _is_person_pipeline_noise(name) is False, (
                f"{name!r} should NOT be noise — it's a person first name"
            )

    def test_single_surname_not_noise(self):
        """Slavic/unusual surnames must NOT be filtered."""
        for name in ["Vymetalova", "Kowalski", "Dubois", "Müller"]:
            assert _is_person_pipeline_noise(name) is False, (
                f"{name!r} should NOT be noise — it's a person surname"
            )

    def test_short_abbreviations_still_noise(self):
        """Short tokens (≤4 chars) that end in consonants → noise."""
        assert _is_person_pipeline_noise("Jr") is True
        assert _is_person_pipeline_noise("Corp") is True
        assert _is_person_pipeline_noise("Att") is True


# ── ADDRESS number-only filter ───────────────────────────────────────────

class TestAddressNumberOnly:
    def test_number_only_is_invalid(self):
        assert _is_address_number_only("12345") is True
        assert _is_address_number_only("42") is True

    def test_alpha_only_is_invalid(self):
        assert _is_address_number_only("Main Street") is True

    def test_mixed_is_valid(self):
        assert _is_address_number_only("123 Main Street") is False
        assert _is_address_number_only("Baker Street 12B") is False

    def test_empty(self):
        assert _is_address_number_only("") is True


# ── German compound noun detection ───────────────────────────────────────

class TestGermanCompound:
    def test_known_compounds(self):
        """These are compound nouns split by dictionary lookup."""
        # The function requires _german_words dict to be loaded.
        # With dicts present, a word like "Spielplatz" = "Spiel" + "platz"
        # should be recognized as a compound.
        # The exact behavior depends on the dictionary content, so we
        # test structural properties.
        assert _is_german_compound_noun("") is False
        assert _is_german_compound_noun("abc") is False  # too short (<6)
        assert _is_german_compound_noun("Hello") is False  # too short


# ── Phone label stripping ────────────────────────────────────────────────

class TestStripPhoneLabels:
    def test_strips_trailing_phone(self):
        text = "123 Main Street\nTel: 555-1234"
        result = _strip_phone_labels_from_address(text)
        assert "555-1234" not in result
        assert "Main Street" in result

    def test_strips_fax_label(self):
        text = "Baker Street 12\nFax: +44 20 7946 0958"
        result = _strip_phone_labels_from_address(text)
        assert "7946" not in result
        assert "Baker Street" in result

    def test_preserves_clean_address(self):
        text = "456 Oak Avenue, Suite 7B"
        assert _strip_phone_labels_from_address(text) == text

    def test_strips_telefono(self):
        text = "Via Roma 10\nTeléfono: 06 1234567"
        result = _strip_phone_labels_from_address(text)
        assert "1234567" not in result

    def test_no_stripping_if_all_phone(self):
        """If removing labels empties the text, return original."""
        text = "Tel: 555-1234"
        result = _strip_phone_labels_from_address(text)
        assert result == text  # returns original to avoid empty


# ── LOCATION noise filter ────────────────────────────────────────────────

class TestLocNoise:
    def test_building_terms_are_noise(self):
        """Building/facility terms are filtered."""
        assert _is_loc_pipeline_noise("building") is True
        assert _is_loc_pipeline_noise("warehouse") is True
        assert _is_loc_pipeline_noise("facility") is True

    def test_real_city_not_noise(self):
        """Proper place names are not in the noise set."""
        assert _is_loc_pipeline_noise("New York City") is False
        assert _is_loc_pipeline_noise("Paris") is False

    def test_short_strings_are_noise(self):
        assert _is_loc_pipeline_noise("A") is True
        assert _is_loc_pipeline_noise("") is True


# ── SpanIndex (from pipeline) ────────────────────────────────────────────

class TestSpanIndex:
    """Unit tests for the bisect-based overlap index."""

    def test_no_overlap_empty(self):
        from core.detection.pipeline import SpanIndex
        idx = SpanIndex()
        assert idx.overlaps(0, 10) is False

    def test_overlap_basic(self):
        from core.detection.pipeline import SpanIndex
        idx = SpanIndex([(0, 10), (20, 30)])
        assert idx.overlaps(5, 15) is True    # overlaps (0,10)
        assert idx.overlaps(10, 20) is False  # exactly between
        assert idx.overlaps(25, 35) is True   # overlaps (20,30)

    def test_no_overlap_adjacent(self):
        from core.detection.pipeline import SpanIndex
        idx = SpanIndex([(0, 10)])
        assert idx.overlaps(10, 20) is False  # adjacent, not overlapping

    def test_add_and_query(self):
        from core.detection.pipeline import SpanIndex
        idx = SpanIndex()
        idx.add(5, 15)
        assert idx.overlaps(10, 20) is True
        assert idx.overlaps(0, 5) is False
        idx.add(20, 30)
        assert idx.overlaps(25, 28) is True

    def test_contained_span(self):
        from core.detection.pipeline import SpanIndex
        idx = SpanIndex([(10, 50)])
        assert idx.overlaps(20, 30) is True  # fully contained
        assert idx.overlaps(0, 100) is True  # fully containing
