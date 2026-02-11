"""Bulletproof tests for the regex PII detector.

Covers edge cases, false positives, international formats,
and financial document noise that the basic test suite doesn't cover.
"""

from core.detection.regex_detector import (
    detect_regex,
    _luhn_check,
    _iban_mod97,
    _is_valid_dutch_bsn,
    _is_valid_portuguese_nif,
    _is_valid_french_ssn,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _types(matches):
    return {getattr(m.pii_type, "value", m.pii_type) for m in matches}


def _of_type(matches, pii_type_str):
    return [m for m in matches
            if getattr(m.pii_type, "value", m.pii_type) == pii_type_str]


# ═══════════════════════════════════════════════════════════════════════════
# NEW VALIDATOR TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDutchBSNValidator:
    def test_valid_bsn(self):
        # Well-known test BSN: 111222333
        # 1*9 + 1*8 + 1*7 + 2*6 + 2*5 + 2*4 + 3*3 + 3*2 + 3*(-1)
        # = 9+8+7+12+10+8+9+6-3 = 66 → 66 % 11 = 0 ✓
        assert _is_valid_dutch_bsn("111222333")

    def test_invalid_bsn(self):
        assert not _is_valid_dutch_bsn("123456789")

    def test_wrong_length(self):
        assert not _is_valid_dutch_bsn("12345678")
        assert not _is_valid_dutch_bsn("1234567890")

    def test_non_numeric(self):
        assert not _is_valid_dutch_bsn("12345678A")


class TestPortugueseNIFValidator:
    def test_valid_nif(self):
        # Test NIF: 123456789
        # Weights: 9,8,7,6,5,4,3,2
        # 1*9 + 2*8 + 3*7 + 4*6 + 5*5 + 6*4 + 7*3 + 8*2
        # = 9+16+21+24+25+24+21+16 = 156
        # 156 % 11 = 2, check = 11-2 = 9 → last digit is 9 ✓
        assert _is_valid_portuguese_nif("123456789")

    def test_invalid_nif(self):
        assert not _is_valid_portuguese_nif("123456780")

    def test_wrong_first_digit(self):
        assert not _is_valid_portuguese_nif("423456789")
        assert not _is_valid_portuguese_nif("723456789")

    def test_wrong_length(self):
        assert not _is_valid_portuguese_nif("12345678")


class TestFrenchSSNValidator:
    def test_valid_ssn(self):
        assert _is_valid_french_ssn("1 85 05 78 006 084 42")

    def test_invalid_gender(self):
        assert not _is_valid_french_ssn("3 85 05 78 006 084 42")

    def test_invalid_month(self):
        assert not _is_valid_french_ssn("1 85 13 78 006 084 42")


# ═══════════════════════════════════════════════════════════════════════════
# FALSE POSITIVE PREVENTION — Financial Documents
# ═══════════════════════════════════════════════════════════════════════════

class TestFinancialDocFalsePositives:
    """These tests verify that common financial document patterns
    don't trigger false PII detections.
    """

    def test_accounting_amounts(self):
        """Dollar amounts should not be detected as anything."""
        text = "Revenue: $1,234,567.89 and expenses of $987,654.32"
        matches = detect_regex(text)
        cc = _of_type(matches, "CREDIT_CARD")
        assert len(cc) == 0

    def test_euro_amounts(self):
        text = "Montant total : 456 789,12 € HT"
        matches = detect_regex(text)
        # Should not detect as phone or SSN
        phone = _of_type(matches, "PHONE")
        ssn = _of_type(matches, "SSN")
        assert len(phone) == 0
        assert len(ssn) == 0

    def test_fiscal_year_references(self):
        """'FY2024', 'exercice 2023' should not match as dates."""
        matches = detect_regex("Results for FY2024 compared to exercice 2023")
        # These are fiscal year refs, not personal dates; should not match
        dates = _of_type(matches, "DATE")
        assert len(dates) == 0

    def test_note_references(self):
        """'Note 5', 'Annexe 3' should be excluded."""
        matches = detect_regex("See Note 5 and Annexe 3 for details.")
        assert len(matches) == 0

    def test_five_digit_totals_not_zip(self):
        """Random 5-digit numbers in tables should NOT match as ZIP codes."""
        text = "Total assets: 52340\nTotal liabilities: 31200"
        addr = _of_type(detect_regex(text), "ADDRESS")
        # ZIP+4 is the only bare ZIP pattern now, so bare 5-digit shouldn't match
        assert len(addr) == 0

    def test_percentage_not_detected(self):
        text = "Interest rate: 3.5% per annum"
        matches = detect_regex(text)
        assert len(matches) == 0

    def test_invoice_numbers_excluded(self):
        text = "Invoice INV-12345 processed. PO#67890 confirmed."
        matches = detect_regex(text)
        assert len(matches) == 0

    def test_section_references_excluded(self):
        text = "As per Section 4.2 and Article 15 of the agreement."
        matches = detect_regex(text)
        assert len(matches) == 0

    def test_accounting_codes_excluded(self):
        text = "Compte 4110 - Clients and Compte 5120 - Banque"
        matches = detect_regex(text)
        ssn = _of_type(matches, "SSN")
        assert len(ssn) == 0


class TestFalsePositivePrevention:
    """Extended false positive prevention tests."""

    def test_product_codes_not_passport(self):
        """Product codes like 'AB1234567' shouldn't match passport
        unless near a passport keyword.
        """
        # Without context — should still match but very low confidence
        pp = _of_type(detect_regex("Model AB1234567 specs"), "PASSPORT")
        # If it matches at all, confidence should be very low
        for p in pp:
            assert p.confidence < 0.55, f"Product code matched passport with conf {p.confidence}"

    def test_reference_numbers_not_dl(self):
        """'A12345678' alone shouldn't match driver's license at high conf."""
        dl = _of_type(detect_regex("Reference A12345678 attached"), "DRIVER_LICENSE")
        for d in dl:
            assert d.confidence < 0.55, f"Reference matched DL with conf {d.confidence}"

    def test_version_string_not_ip(self):
        text = "Updated to version 2.3.1 successfully."
        ip = _of_type(detect_regex(text), "IP_ADDRESS")
        assert len(ip) == 0

    def test_timestamps_not_phone(self):
        text = "Meeting at 14:30:00 in Conference Room B"
        phone = _of_type(detect_regex(text), "PHONE")
        assert len(phone) == 0

    def test_page_numbers_not_ssn(self):
        text = "See page 123 for details"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) == 0

    def test_clean_prose(self):
        """Normal text with no PII should produce zero matches."""
        text = (
            "The company reported strong quarterly earnings driven by "
            "increased demand in the technology sector. Revenue grew by "
            "fifteen percent compared to the same period last year."
        )
        matches = detect_regex(text)
        assert len(matches) == 0

    def test_french_financial_prose(self):
        """French financial text should not produce spurious matches."""
        text = (
            "Les états financiers ont été préparés conformément aux "
            "normes comptables canadiennes pour les entreprises à capital "
            "fermé. Le résultat net de l'exercice est de 125 000 $."
        )
        matches = detect_regex(text)
        # Should not match anything as PII
        ssn = _of_type(matches, "SSN")
        phone = _of_type(matches, "PHONE")
        assert len(ssn) == 0
        assert len(phone) == 0


# ═══════════════════════════════════════════════════════════════════════════
# INTERNATIONAL SSN / NATIONAL ID PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

class TestDutchBSN:
    def test_bsn_with_label(self):
        text = "BSN: 111222333"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_bsn_label_value(self):
        text = "Burgerservicenummer: 111222333"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_invalid_bsn_rejected(self):
        """BSN that fails both 11-check and NIF mod-11 should be rejected."""
        text = "BSN: 111111111"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) == 0


class TestPortugueseNIF:
    def test_nif_with_label(self):
        text = "NIF: 123456789"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_nif_contribuinte_label(self):
        text = "Número de contribuinte: 123456789"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_invalid_nif_rejected(self):
        text = "NIF: 123456780"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) == 0


# ═══════════════════════════════════════════════════════════════════════════
# INTERNATIONAL DATE PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianDates:
    def test_italian_month(self):
        dt = _of_type(detect_regex("Nato il 15 gennaio 1985"), "DATE")
        assert len(dt) >= 1

    def test_italian_december(self):
        dt = _of_type(detect_regex("Data: 31 dicembre 2023"), "DATE")
        assert len(dt) >= 1


class TestDutchDates:
    def test_dutch_month(self):
        dt = _of_type(detect_regex("Geboren op 15 januari 1985"), "DATE")
        assert len(dt) >= 1

    def test_dutch_march(self):
        dt = _of_type(detect_regex("Datum: 1 maart 2024"), "DATE")
        assert len(dt) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# POSTAL CODE EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestPostalCodes:
    def test_french_postal_with_city(self):
        addr = _of_type(detect_regex("75008 Paris"), "ADDRESS")
        assert len(addr) >= 1

    def test_french_cedex(self):
        addr = _of_type(detect_regex("92042 Paris La Défense Cedex"), "ADDRESS")
        assert len(addr) >= 1

    def test_german_postal_with_city(self):
        addr = _of_type(detect_regex("D-10117 Berlin"), "ADDRESS")
        assert len(addr) >= 1

    def test_uk_postcode(self):
        addr = _of_type(detect_regex("SW1A 1AA"), "ADDRESS")
        assert len(addr) >= 1

    def test_canadian_postal(self):
        addr = _of_type(detect_regex("K1A 0B1"), "ADDRESS")
        assert len(addr) >= 1

    def test_dutch_postal(self):
        addr = _of_type(detect_regex("1234 AB"), "ADDRESS")
        assert len(addr) >= 1

    def test_belgian_postal_with_prefix(self):
        addr = _of_type(detect_regex("B-1000 Bruxelles"), "ADDRESS")
        assert len(addr) >= 1

    def test_swiss_postal_with_prefix(self):
        addr = _of_type(detect_regex("CH-8001 Zürich"), "ADDRESS")
        assert len(addr) >= 1

    def test_zip_plus_four(self):
        addr = _of_type(detect_regex("ZIP: 90210-1234"), "ADDRESS")
        assert len(addr) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# ORG PATTERN EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════

class TestOrgEdgeCases:
    def test_numbered_company_quebec(self):
        org = _of_type(detect_regex("9169270 Canada inc."), "ORG")
        assert len(org) >= 1

    def test_numbered_company_german(self):
        org = _of_type(detect_regex("12345678 München GmbH"), "ORG")
        assert len(org) >= 1

    def test_french_sarl(self):
        org = _of_type(detect_regex("Cabinet Dupont SARL"), "ORG")
        assert len(org) >= 1

    def test_french_groupe(self):
        org = _of_type(detect_regex("Groupe Michelin"), "ORG")
        assert len(org) >= 1

    def test_english_corp(self):
        org = _of_type(detect_regex("Globex Corp."), "ORG")
        assert len(org) >= 1

    def test_spanish_sl(self):
        org = _of_type(detect_regex("Empresas Reunidas S.L."), "ORG")
        assert len(org) >= 1

    def test_german_gmbh(self):
        org = _of_type(detect_regex("Müller & Söhne GmbH"), "ORG")
        assert len(org) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BOOST VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestContextBoost:
    def test_ssn_boost_with_keyword(self):
        with_ctx = detect_regex("Social Security Number: 123-45-6789")
        without_ctx = detect_regex("Reference 123-45-6789 attached")
        ssn_w = _of_type(with_ctx, "SSN")
        ssn_wo = _of_type(without_ctx, "SSN")
        assert len(ssn_w) >= 1
        assert len(ssn_wo) >= 1
        assert ssn_w[0].confidence > ssn_wo[0].confidence

    def test_iban_boost_with_keyword(self):
        with_ctx = detect_regex("IBAN: DE89370400440532013000")
        without_ctx = detect_regex("Code DE89370400440532013000 here")
        iban_w = _of_type(with_ctx, "IBAN")
        iban_wo = _of_type(without_ctx, "IBAN")
        assert len(iban_w) >= 1
        if iban_wo:
            assert iban_w[0].confidence >= iban_wo[0].confidence

    def test_phone_boost_france(self):
        with_ctx = detect_regex("Téléphone: 06 12 34 56 78")
        without_ctx = detect_regex("Code 06 12 34 56 78 ici")
        ph_w = _of_type(with_ctx, "PHONE")
        ph_wo = _of_type(without_ctx, "PHONE")
        assert len(ph_w) >= 1
        assert len(ph_wo) >= 1
        assert ph_w[0].confidence >= ph_wo[0].confidence


# ═══════════════════════════════════════════════════════════════════════════
# LABEL-VALUE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

class TestLabelValueExtraction:
    def test_passport_after_label(self):
        pp = _of_type(detect_regex("Passport No: AB123456"), "PASSPORT")
        assert len(pp) >= 1

    def test_french_passport_label(self):
        pp = _of_type(detect_regex("Passeport N° : 12AB34567"), "PASSPORT")
        assert len(pp) >= 1

    def test_dl_after_label(self):
        dl = _of_type(detect_regex("Driver's License: B1234567"), "DRIVER_LICENSE")
        assert len(dl) >= 1

    def test_french_dl_label(self):
        dl = _of_type(detect_regex("Permis de conduire: 1234567890"), "DRIVER_LICENSE")
        assert len(dl) >= 1

    def test_ssn_after_label(self):
        ssn = _of_type(detect_regex("SSN: 123-45-6789"), "SSN")
        assert len(ssn) >= 1
        # Label extraction gives higher confidence
        assert ssn[0].confidence >= 0.90

    def test_dob_after_label(self):
        dt = _of_type(detect_regex("Date of Birth: 15/03/1985"), "DATE")
        assert len(dt) >= 1
        assert dt[0].confidence >= 0.90

    def test_french_dob_label(self):
        dt = _of_type(detect_regex("Né le : 15/03/1985"), "DATE")
        assert len(dt) >= 1

    def test_email_after_label(self):
        em = _of_type(detect_regex("Email: user@example.com"), "EMAIL")
        assert len(em) >= 1

    def test_phone_after_label(self):
        ph = _of_type(detect_regex("Phone: +33 6 12 34 56 78"), "PHONE")
        assert len(ph) >= 1

    def test_address_after_label_stops_at_newline(self):
        text = "Address: 123 Main Street, Springfield IL\nPhone: 555-1234"
        addr = _of_type(detect_regex(text), "ADDRESS")
        assert len(addr) >= 1
        # Should not capture the phone line
        for a in addr:
            assert "Phone" not in a.text

    def test_vat_after_label(self):
        custom = _of_type(detect_regex("TVA: FR12345678901"), "CUSTOM")
        assert len(custom) >= 1

    def test_dutch_bsn_after_label(self):
        ssn = _of_type(detect_regex("BSN: 111222333"), "SSN")
        assert len(ssn) >= 1

    def test_portuguese_nif_after_label(self):
        ssn = _of_type(detect_regex("NIF: 123456789"), "SSN")
        assert len(ssn) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# OVERLAP RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class TestOverlapResolution:
    def test_overlapping_keeps_higher_confidence(self):
        """When two patterns match the same text, the higher-confidence
        one should win."""
        # "SSN: 123-45-6789" — both standalone SSN and label-value SSN match
        text = "SSN: 123-45-6789"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1
        # Label-value should give higher confidence
        assert ssn[0].confidence >= 0.90

    def test_email_not_displaced_by_person(self):
        """Email pattern should not be displaced by name extraction."""
        text = "Contact John.Smith@example.com for info"
        em = _of_type(detect_regex(text), "EMAIL")
        assert len(em) >= 1
        assert "John.Smith@example.com" in em[0].text


# ═══════════════════════════════════════════════════════════════════════════
# EDGE CASES — Tricky real-world patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_multiline_address(self):
        """Multi-line address with postal code."""
        text = "42 rue de la Paix\n75002 Paris"
        addr = _of_type(detect_regex(text), "ADDRESS")
        assert len(addr) >= 1

    def test_phone_in_parentheses(self):
        text = "(+33) 6 12 34 56 78"
        ph = _of_type(detect_regex(text), "PHONE")
        assert len(ph) >= 1

    def test_iban_with_spaces(self):
        text = "FR76 3000 6000 0112 3456 7890 189"
        iban = _of_type(detect_regex(text), "IBAN")
        assert len(iban) >= 1

    def test_credit_card_amex(self):
        text = "3782 822463 10005"
        cc = _of_type(detect_regex(text), "CREDIT_CARD")
        assert len(cc) >= 1

    def test_ipv4_boundary(self):
        text = "Server 255.255.255.0 netmask"
        ip = _of_type(detect_regex(text), "IP_ADDRESS")
        assert len(ip) >= 1

    def test_gps_coordinates(self):
        text = "Location: 48.8566, 2.3522"
        loc = _of_type(detect_regex(text), "LOCATION")
        assert len(loc) >= 1

    def test_hyphenated_french_name(self):
        text = "Mme Marie-Claire Dupont-Martin"
        person = _of_type(detect_regex(text), "PERSON")
        assert len(person) >= 1

    def test_dense_pii_document(self):
        """Simulate a form with many PII types."""
        text = (
            "Patient: John Smith\n"
            "DOB: 15/03/1985\n"
            "SSN: 123-45-6789\n"
            "Phone: (555) 123-4567\n"
            "Email: john.smith@example.com\n"
            "Address: 123 Main Street, Springfield IL\n"
        )
        types = _types(detect_regex(text))
        assert "PERSON" in types
        assert "SSN" in types
        assert "PHONE" in types
        assert "EMAIL" in types

    def test_italian_codice_fiscale_context(self):
        text = "Codice fiscale: RSSMRA85M01H501Z"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_belgian_national_number(self):
        text = "Rijksregisternummer: 85.05.15-123.45"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_uk_national_insurance(self):
        text = "National Insurance: AB123456C"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_spanish_dni(self):
        text = "DNI: 12345678A"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_eu_vat_number(self):
        text = "VAT: FR12345678901"
        custom = _of_type(detect_regex(text), "CUSTOM")
        assert len(custom) >= 1
