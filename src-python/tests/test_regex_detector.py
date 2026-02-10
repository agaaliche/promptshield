"""Tests for the regex PII detector."""

from core.detection.regex_detector import detect_regex, _luhn_check, _iban_mod97


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _types(matches):
    """Return a set of pii_type strings from matches."""
    return {getattr(m.pii_type, "value", m.pii_type) for m in matches}


def _of_type(matches, pii_type_str):
    """Filter matches by PII type string value."""
    return [m for m in matches
            if getattr(m.pii_type, "value", m.pii_type) == pii_type_str]


# ═══════════════════════════════════════════════════════════════════════════
# Validation unit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidators:
    def test_luhn_valid(self):
        assert _luhn_check("4111111111111111")   # Classic Visa test number

    def test_luhn_invalid(self):
        assert not _luhn_check("4111111111111112")

    def test_iban_mod97_valid(self):
        assert _iban_mod97("DE89370400440532013000")
        assert _iban_mod97("FR76 3000 6000 0112 3456 7890 189")

    def test_iban_mod97_invalid(self):
        assert not _iban_mod97("DE00370400440532013000")
        assert not _iban_mod97("XX1234")


# ═══════════════════════════════════════════════════════════════════════════
# Core PII patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestEmail:
    def test_basic(self):
        matches = detect_regex("Contact me at john.doe@example.com for details.")
        em = _of_type(matches, "EMAIL")
        assert len(em) == 1
        assert em[0].text == "john.doe@example.com"
        assert em[0].confidence >= 0.95

    def test_plus_address(self):
        em = _of_type(detect_regex("user+tag@company.co.uk"), "EMAIL")
        assert len(em) == 1

    def test_no_false_positive(self):
        em = _of_type(detect_regex("filename.txt or v2.0 release"), "EMAIL")
        assert len(em) == 0


class TestSSN:
    def test_us_dashed(self):
        text = "My SSN is 123-45-6789, please keep it private."
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) == 1
        assert ssn[0].text == "123-45-6789"

    def test_us_spaced(self):
        text = "SSN: 123 45 6789 on file."
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_context_boost(self):
        # With context keyword "SSN" within range, confidence should be boosted
        with_ctx = detect_regex("SSN: 123-45-6789")
        without_ctx = detect_regex("number 123-45-6789 here")
        ssn_w = _of_type(with_ctx, "SSN")
        ssn_wo = _of_type(without_ctx, "SSN")
        assert ssn_w[0].confidence > ssn_wo[0].confidence

    def test_french_nir(self):
        text = "N° SS : 1 85 05 78 006 084 42"
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

    def test_spanish_nie(self):
        text = "NIE: X1234567A"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1

    def test_italian_codice_fiscale(self):
        text = "Codice Fiscale: RSSMRA85M01H501Z"
        matches = detect_regex(text)
        ssn = _of_type(matches, "SSN")
        assert len(ssn) >= 1
        assert "RSSMRA85M01H501Z" in ssn[0].text

    def test_belgian_nn(self):
        text = "Rijksregisternummer: 85.05.15-123.45"
        ssn = _of_type(detect_regex(text), "SSN")
        assert len(ssn) >= 1


class TestPhone:
    def test_us_parens(self):
        matches = detect_regex("Call (555) 123-4567 now.")
        ph = _of_type(matches, "PHONE")
        assert len(ph) >= 1
        assert "(555) 123-4567" in ph[0].text

    def test_international_plus(self):
        ph = _of_type(detect_regex("Tel: +1-555-987-6543"), "PHONE")
        assert len(ph) >= 1

    def test_french(self):
        ph = _of_type(detect_regex("Tél: 06 12 34 56 78"), "PHONE")
        assert len(ph) >= 1

    def test_french_intl(self):
        ph = _of_type(detect_regex("Phone: +33 6 12 34 56 78"), "PHONE")
        assert len(ph) >= 1

    def test_us_bare_with_context(self):
        # Bare US phone has low confidence, but with keyword it should match
        ph = _of_type(detect_regex("Phone: 555-123-4567"), "PHONE")
        assert len(ph) >= 1

    def test_toll_free(self):
        ph = _of_type(detect_regex("Call 1-800-555-1234"), "PHONE")
        assert len(ph) >= 1


class TestCreditCard:
    def test_visa_separated(self):
        cc = _of_type(detect_regex("Card: 4111 1111 1111 1111"), "CREDIT_CARD")
        assert len(cc) == 1

    def test_luhn_reject(self):
        # Invalid Luhn should be rejected
        cc = _of_type(detect_regex("Number: 1234 5678 9012 3456"), "CREDIT_CARD")
        assert len(cc) == 0

    def test_amex(self):
        cc = _of_type(detect_regex("Card: 3782 822463 10005"), "CREDIT_CARD")
        assert len(cc) >= 1


class TestIBAN:
    def test_valid_iban_with_label(self):
        text = "IBAN: DE89370400440532013000"
        iban = _of_type(detect_regex(text), "IBAN")
        assert len(iban) >= 1

    def test_valid_iban_standalone(self):
        # DE89... is a well-known valid test IBAN
        text = "Wire to DE89 3704 0044 0532 0130 00 please."
        iban = _of_type(detect_regex(text), "IBAN")
        assert len(iban) >= 1

    def test_invalid_iban_rejected(self):
        text = "IBAN: DE00370400440532013000"
        iban = _of_type(detect_regex(text), "IBAN")
        assert len(iban) == 0

    def test_french_iban(self):
        text = "IBAN : FR76 3000 6000 0112 3456 7890 189"
        iban = _of_type(detect_regex(text), "IBAN")
        assert len(iban) >= 1


class TestDate:
    def test_numeric_with_context(self):
        text = "Date of Birth: 15/03/1985"
        dt = _of_type(detect_regex(text), "DATE")
        assert len(dt) >= 1

    def test_english_month(self):
        dt = _of_type(detect_regex("Born January 15, 1985"), "DATE")
        assert len(dt) >= 1

    def test_english_day_first(self):
        dt = _of_type(detect_regex("Date of Birth: 15 March 2000"), "DATE")
        assert len(dt) >= 1

    def test_french_month(self):
        dt = _of_type(detect_regex("Né le 15 janvier 1985"), "DATE")
        assert len(dt) >= 1

    def test_german_month(self):
        dt = _of_type(detect_regex("Geboren am 15. Januar 1985"), "DATE")
        assert len(dt) >= 1

    def test_invalid_date_rejected(self):
        dt = _of_type(detect_regex("Date of Birth: 42/13/1985"), "DATE")
        assert len(dt) == 0

    def test_iso_format(self):
        dt = _of_type(detect_regex("DOB: 1985-03-15"), "DATE")
        assert len(dt) >= 1


class TestIPAddress:
    def test_two_ips(self):
        matches = detect_regex("Server: 192.168.1.100 backup: 10.0.0.1")
        ip = _of_type(matches, "IP_ADDRESS")
        assert len(ip) == 2

    def test_ipv6(self):
        ip = _of_type(
            detect_regex("Host: 2001:0db8:85a3:0000:0000:8a2e:0370:7334"),
            "IP_ADDRESS",
        )
        assert len(ip) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Identity documents
# ═══════════════════════════════════════════════════════════════════════════

class TestPassport:
    def test_eu_format(self):
        pp = _of_type(detect_regex("Passport: AB1234567"), "PASSPORT")
        assert len(pp) >= 1

    def test_german_format(self):
        pp = _of_type(detect_regex("Reisepass: C01X00T47"), "PASSPORT")
        assert len(pp) >= 1

    def test_label_boost(self):
        with_label = detect_regex("Passport No: AB1234567")
        without = detect_regex("ref AB1234567 here")
        pp_w = _of_type(with_label, "PASSPORT")
        pp_wo = _of_type(without, "PASSPORT")
        assert len(pp_w) >= 1
        if pp_wo:
            assert pp_w[0].confidence > pp_wo[0].confidence


class TestDriverLicense:
    def test_us_format(self):
        dl = _of_type(detect_regex("DL: A123-4567-8901"), "DRIVER_LICENSE")
        assert len(dl) >= 1

    def test_label_extraction(self):
        dl = _of_type(detect_regex("Driver's License: B1234567"), "DRIVER_LICENSE")
        assert len(dl) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Address patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestAddress:
    def test_english_street(self):
        addr = _of_type(detect_regex("Lives at 123 Main Street, Springfield"), "ADDRESS")
        assert len(addr) >= 1

    def test_french_street(self):
        addr = _of_type(detect_regex("Adresse: 42 rue de la Paix"), "ADDRESS")
        assert len(addr) >= 1

    def test_german_street(self):
        addr = _of_type(
            detect_regex("Anschrift: Hauptstraße 15"),
            "ADDRESS",
        )
        assert len(addr) >= 1

    def test_po_box(self):
        addr = _of_type(detect_regex("Mail to P.O. Box 1234"), "ADDRESS")
        assert len(addr) >= 1

    def test_label_extraction(self):
        addr = _of_type(
            detect_regex("Address: 456 Elm Road, Suite 200, Chicago IL"),
            "ADDRESS",
        )
        assert len(addr) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Person / Org patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestPerson:
    def test_english_title(self):
        p = _of_type(detect_regex("Dear Mr. John Smith,"), "PERSON")
        assert len(p) >= 1

    def test_french_title(self):
        p = _of_type(detect_regex("Chère Mme Lefèvre Dupont,"), "PERSON")
        assert len(p) >= 1

    def test_german_title(self):
        p = _of_type(detect_regex("Sehr geehrter Herr Schmidt,"), "PERSON")
        assert len(p) >= 1

    def test_spanish_title(self):
        p = _of_type(detect_regex("Estimado Sr. García López,"), "PERSON")
        assert len(p) >= 1

    def test_label_extraction(self):
        p = _of_type(detect_regex("Patient: Jane Doe"), "PERSON")
        assert len(p) >= 1
        assert "Jane Doe" in p[0].text

    def test_french_label(self):
        p = _of_type(detect_regex("Nom : Dupont"), "PERSON")
        assert len(p) >= 1


class TestOrg:
    def test_french_legal_suffix(self):
        org = _of_type(detect_regex("Facture de Dupont Consulting SAS"), "ORG")
        assert len(org) >= 1

    def test_english_legal_suffix(self):
        org = _of_type(detect_regex("Contract with Globex Corp."), "ORG")
        assert len(org) >= 1

    def test_french_prefix(self):
        org = _of_type(detect_regex("Envoyé par Groupe Michelin"), "ORG")
        assert len(org) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# False positive prevention
# ═══════════════════════════════════════════════════════════════════════════

class TestFalsePositives:
    def test_clean_text(self):
        matches = detect_regex("The quick brown fox jumps over the lazy dog.")
        assert len(matches) == 0

    def test_page_numbers_excluded(self):
        matches = detect_regex("See page 123 for details. Refer to Section 4.2.")
        # Should not produce SSN-like matches on "123"
        ssn = _of_type(matches, "SSN")
        assert len(ssn) == 0

    def test_version_numbers_excluded(self):
        matches = detect_regex("Updated to version 2.3.1 successfully.")
        ip = _of_type(matches, "IP_ADDRESS")
        assert len(ip) == 0

    def test_currency_excluded(self):
        matches = detect_regex("Total: $1,234.56 due by end of month.")
        # Should not detect as credit card
        cc = _of_type(matches, "CREDIT_CARD")
        assert len(cc) == 0

    def test_percentage_excluded(self):
        matches = detect_regex("Growth of 15.3% in Q2.")
        assert len(matches) == 0

    def test_timestamps_excluded(self):
        matches = detect_regex("Meeting at 14:30 in room 5.")
        phone = _of_type(matches, "PHONE")
        assert len(phone) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Multiple types in one text
# ═══════════════════════════════════════════════════════════════════════════

class TestMultipleTypes:
    def test_mixed_pii(self):
        text = "Name: John Smith, SSN: 123-45-6789, email: john@test.com"
        types = _types(detect_regex(text))
        assert "SSN" in types
        assert "EMAIL" in types

    def test_dense_pii(self):
        text = (
            "Patient: Jane Doe\n"
            "DOB: 15/03/1985\n"
            "SSN: 123-45-6789\n"
            "Phone: (555) 123-4567\n"
            "Email: jane@example.com\n"
        )
        types = _types(detect_regex(text))
        assert "PERSON" in types
        assert "SSN" in types
        assert "PHONE" in types
        assert "EMAIL" in types

