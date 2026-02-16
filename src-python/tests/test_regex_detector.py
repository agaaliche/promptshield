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

    def test_french_body_text_lowercase_company(self):
        """Body text: 'Les entreprises de restauration B.N. ltée' with lowercase words."""
        text = "filiale, Les entreprises de restauration B.N. ltée, ont fusionné."
        org = _of_type(detect_regex(text), "ORG")
        assert len(org) >= 1
        assert any("entreprises" in m.text.lower() and "ltée" in m.text.lower() for m in org)

    def test_french_numbered_company_quebec(self):
        """Quebec-style numbered company: '9425-7524 Québec inc.'"""
        text = "la société 9425-7524 Québec inc. et sa filiale"
        org = _of_type(detect_regex(text), "ORG")
        assert len(org) >= 1
        assert any("9425-7524" in m.text for m in org)

    def test_allcaps_header_with_abbreviation(self):
        """ALL CAPS header: 'LES ENTREPRISES DE RESTAURATION B.N. LTÉE'"""
        text = "LES ENTREPRISES DE RESTAURATION B.N. LTÉE"
        org = _of_type(detect_regex(text), "ORG")
        assert len(org) >= 1
        assert any("B.N." in m.text for m in org)

    def test_no_false_positive_french_body_text(self):
        """Normal French text without company names should not match."""
        texts = [
            "La direction est responsable de la préparation et de la présentation.",
            "Les notes complémentaires font partie intégrante de ces états financiers.",
            "Le rapport comprend les informations financières historiques.",
        ]
        for text in texts:
            org = _of_type(detect_regex(text), "ORG")
            assert len(org) == 0, f"False positive in: {text}"


class TestRotationFilter:
    """Tests for _is_rotated_word in the text extraction pipeline."""

    def test_periods_not_rotated(self):
        """B.N. — periods at different y-position should not flag rotation."""
        from core.ingestion.loader import _is_rotated_word
        # Simulated from real PDF data: B=545.12, .=540.89, N=545.01, .=540.89
        y_centers = [545.12, 540.89, 545.01, 540.89]
        heights = [10.73, 2.6, 10.95, 2.6]
        assert not _is_rotated_word(y_centers, heights)

    def test_comma_not_rotated(self):
        """'2023,' — trailing comma should not flag rotation."""
        from core.ingestion.loader import _is_rotated_word
        y_centers = [518.83, 518.77, 518.83, 518.77, 514.67]
        heights = [7.57, 7.69, 7.57, 7.69, 2.93]
        assert not _is_rotated_word(y_centers, heights)

    def test_apostrophe_not_rotated(self):
        """'l'exercice' — apostrophe at different y-pos should not flag rotation."""
        from core.ingestion.loader import _is_rotated_word
        y_centers = [461.33, 463.4, 459.95, 459.94, 459.97, 459.95, 460.74, 461.33, 460.74, 459.87]
        heights = [7.77, 3.26, 5.31, 5.0, 5.31, 5.16, 5.3, 7.77, 5.3, 5.31]
        assert not _is_rotated_word(y_centers, heights)

    def test_accented_capital_not_rotated(self):
        """'Équipements' — accented É with taller bbox should not flag rotation."""
        from core.ingestion.loader import _is_rotated_word
        y_centers = [203.39, 199.88, 200.91, 202.37, 199.88, 200.99, 201.06, 200.99, 201.06, 201.78, 200.99]
        heights = [9.83, 7.51, 5.14, 7.77, 7.51, 5.31, 5.16, 5.31, 5.16, 6.72, 5.3]
        assert not _is_rotated_word(y_centers, heights)

    def test_truly_rotated_detected(self):
        """Simulated 30° rotated text should be detected as rotated."""
        from core.ingestion.loader import _is_rotated_word
        # 8 chars at 30° rotation: progressive y-shift of ~3pt per char
        y_centers = [100.0, 103.0, 106.0, 109.0, 112.0, 115.0, 118.0, 121.0]
        heights = [6.0] * 8
        assert _is_rotated_word(y_centers, heights)

    def test_single_char_not_rotated(self):
        """Single character should never be considered rotated."""
        from core.ingestion.loader import _is_rotated_word
        assert not _is_rotated_word([100.0], [6.0])

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


# ═══════════════════════════════════════════════════════════════════════════
# Cross-line ORG boundary detection
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossLineOrg:
    """Tests for _detect_cross_line_orgs — company names spanning line breaks."""

    def _matches(self, text):
        from core.detection.pipeline import _detect_cross_line_orgs
        return _detect_cross_line_orgs(text)

    def test_company_split_at_connecting_word(self):
        """Company name with connecting word on the next line."""
        text = "Nous avons audite Les Entreprises\nde Restauration B.N. Ltee pour"
        matches = self._matches(text)
        assert len(matches) >= 1
        assert any("Entreprises" in m.text and "Ltee" in m.text for m in matches)

    def test_suffix_on_next_line(self):
        """Legal suffix (Inc) appears on the next line."""
        text = "le rapport de Societe Generale\ndu Transport Inc dans le cadre"
        matches = self._matches(text)
        assert len(matches) >= 1
        assert any("Inc" in m.text for m in matches)

    def test_all_caps_across_lines(self):
        """ALL CAPS company name split across two lines."""
        text = "LES ENTREPRISES DE RESTAURATION\nB.N. LTEE"
        matches = self._matches(text)
        assert len(matches) >= 1
        assert any("LTEE" in m.text and "ENTREPRISES" in m.text for m in matches)

    def test_numbered_company_across_lines(self):
        """Quebec numbered company wrapping across a line break."""
        text = "la societe 9425-7524\nQuebec inc. a ete constituee"
        matches = self._matches(text)
        assert len(matches) >= 1
        assert any("9425-7524" in m.text and "inc" in m.text for m in matches)

    def test_no_false_positive_normal_text(self):
        """Normal French prose should not trigger cross-line ORG detection."""
        text = "il fait beau aujourd hui\net dans le jardin les fleurs"
        matches = self._matches(text)
        assert len(matches) == 0

    def test_company_fully_on_one_line_not_duplicated(self):
        """Company name entirely on one line should NOT be detected here."""
        text = "Les Entreprises de Restauration B.N. Ltee\net les autres"
        matches = self._matches(text)
        assert len(matches) == 0

    def test_no_match_when_no_newlines(self):
        """Text without newlines produces no cross-line matches."""
        text = "Les Entreprises de Restauration B.N. Ltee"
        matches = self._matches(text)
        assert len(matches) == 0

    def test_gmbh_across_lines(self):
        """German GmbH suffix on next line."""
        text = "Die Gesellschaft Muller und Schmidt\nTechnik GmbH hat berichtet"
        matches = self._matches(text)
        assert len(matches) >= 1
        assert any("GmbH" in m.text for m in matches)


# ═══════════════════════════════════════════════════════════════════════════
# Linked-group (multi-line siblings) pipeline tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLinkedGroup:
    """Tests that multi-line detections produce per-line sibling regions
    sharing a linked_group ID."""

    def _make_page_data(self, full_text, blocks):
        from models.schemas import PageData, TextBlock, BBox
        text_blocks = []
        for i, (txt, x0, y0, x1, y1) in enumerate(blocks):
            text_blocks.append(TextBlock(
                text=txt,
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                word_index=i,
            ))
        return PageData(
            page_number=1,
            width=612.0,
            height=792.0,
            bitmap_path="/tmp/dummy.png",
            text_blocks=text_blocks,
            full_text=full_text,
        )

    def test_multiline_org_creates_linked_siblings(self):
        """A 2-line ORG match should produce 2 regions with same linked_group."""
        from core.detection.pipeline import _merge_detections
        from core.detection.regex_detector import RegexMatch
        from models.schemas import PIIType

        # Simulate: "Societe Generale\ndu Transport Inc"
        # Line 1: y=100..110, Line 2: y=120..130
        text = "Societe Generale\ndu Transport Inc"
        blocks = [
            ("Societe", 10, 100, 60, 110),
            ("Generale", 65, 100, 120, 110),
            ("du", 10, 120, 25, 130),
            ("Transport", 30, 120, 90, 130),
            ("Inc", 95, 120, 115, 130),
        ]
        page_data = self._make_page_data(text, blocks)

        regex_matches = [
            RegexMatch(
                start=0, end=len(text),
                text=text, pii_type=PIIType.ORG, confidence=0.90,
            ),
        ]

        regions = _merge_detections(regex_matches, [], [], page_data)
        org_regions = [r for r in regions if r.pii_type == PIIType.ORG]

        # Should have 2 linked siblings (one per line)
        assert len(org_regions) == 2
        assert org_regions[0].linked_group is not None
        assert org_regions[0].linked_group == org_regions[1].linked_group
        # Each sibling has a per-line bbox (not a merged tall rectangle)
        assert org_regions[0].bbox.y1 <= 115  # line 1
        assert org_regions[1].bbox.y0 >= 115  # line 2

    def test_single_line_org_no_linked_group(self):
        """A single-line ORG should have linked_group=None."""
        from core.detection.pipeline import _merge_detections
        from core.detection.regex_detector import RegexMatch
        from models.schemas import PIIType

        text = "Societe Generale Inc"
        blocks = [
            ("Societe", 10, 100, 60, 110),
            ("Generale", 65, 100, 120, 110),
            ("Inc", 125, 100, 145, 110),
        ]
        page_data = self._make_page_data(text, blocks)

        regex_matches = [
            RegexMatch(
                start=0, end=len(text),
                text=text, pii_type=PIIType.ORG, confidence=0.90,
            ),
        ]

        regions = _merge_detections(regex_matches, [], [], page_data)
        org_regions = [r for r in regions if r.pii_type == PIIType.ORG]
        assert len(org_regions) == 1
        assert org_regions[0].linked_group is None

    def test_linked_siblings_share_text(self):
        """Both siblings should carry the full match text."""
        from core.detection.pipeline import _merge_detections
        from core.detection.regex_detector import RegexMatch
        from models.schemas import PIIType

        text = "Les Entreprises\nde Restauration Ltee"
        blocks = [
            ("Les", 10, 100, 30, 110),
            ("Entreprises", 35, 100, 100, 110),
            ("de", 10, 120, 22, 130),
            ("Restauration", 27, 120, 100, 130),
            ("Ltee", 105, 120, 130, 130),
        ]
        page_data = self._make_page_data(text, blocks)

        regex_matches = [
            RegexMatch(
                start=0, end=len(text),
                text=text, pii_type=PIIType.ORG, confidence=0.90,
            ),
        ]

        regions = _merge_detections(regex_matches, [], [], page_data)
        org_regions = [r for r in regions if r.pii_type == PIIType.ORG]
        assert len(org_regions) == 2
        # Both carry the full text
        for r in org_regions:
            assert r.text == text


# ═══════════════════════════════════════════════════════════════════════════
# Contract-domain patterns
# ═══════════════════════════════════════════════════════════════════════════


class TestBIC:
    """BIC / SWIFT code detection."""

    def test_bic_with_label(self):
        text = "BIC: BNPAFRPP"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("BNPAFRPP" in m.text for m in matches)

    def test_bic_11_char(self):
        text = "SWIFT Code: DEUTDEFF500"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("DEUTDEFF500" in m.text for m in matches)

    def test_bic_invalid_country(self):
        """BIC with invalid country code should be rejected by validation."""
        text = "Code: ABCDXX2L"
        matches = _of_type(detect_regex(text), "CUSTOM")
        bic_matches = [m for m in matches if len(m.text.strip()) in (8, 11)
                       and m.text.strip().isalnum()]
        assert len(bic_matches) == 0


class TestSIREN:
    """French SIREN / SIRET detection."""

    def test_siren_label(self):
        text = "SIREN: 362 521 879"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert any("362 521 879" in m.text for m in matches)

    def test_siret_label(self):
        text = "SIRET: 362 521 879 00034"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert any("362 521 879 00034" in m.text for m in matches)

    def test_rcs(self):
        text = "RCS Paris 362 521 879"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert any("362 521 879" in m.text for m in matches)


class TestHRB:
    """German Handelsregister detection."""

    def test_hrb_standalone(self):
        text = "eingetragen im Handelsregister HRB 137077"
        matches = _of_type(detect_regex(text, detection_language="de"), "CUSTOM")
        assert any("HRB 137077" in m.text for m in matches)

    def test_hrb_label(self):
        text = "Handelsregister: München HRB 12345"
        matches = _of_type(detect_regex(text, detection_language="de"), "CUSTOM")
        assert len(matches) >= 1


class TestEIN:
    """US EIN detection."""

    def test_ein_with_context(self):
        text = "EIN: 12-3456789"
        matches = _of_type(detect_regex(text, detection_language="en"), "SSN")
        assert any("12-3456789" in m.text for m in matches)


class TestSpanishCIF:
    """Spanish CIF detection."""

    def test_cif_standalone(self):
        text = "CIF: B12345678"
        matches = _of_type(detect_regex(text, detection_language="es"), "CUSTOM")
        assert any("B12345678" in m.text for m in matches)

    def test_cif_with_label(self):
        text = "N.I.F: A87654321"
        matches = _of_type(detect_regex(text, detection_language="es"), "CUSTOM")
        assert any("A87654321" in m.text for m in matches)


class TestSignatory:
    """Contract signatory label-value patterns."""

    def test_signed_by_en(self):
        text = "Signed by: John William Smith"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("John William Smith" in m.text for m in matches)

    def test_signe_par_fr(self):
        text = "Signé par: Jean-Pierre Dupont"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Jean-Pierre Dupont" in m.text for m in matches)

    def test_firmado_por_es(self):
        text = "Firmado por: María García López"
        matches = _of_type(detect_regex(text, detection_language="es"), "PERSON")
        assert any("García López" in m.text for m in matches)

    def test_unterschrieben_von_de(self):
        text = "Unterschrieben von: Hans Müller"
        matches = _of_type(detect_regex(text, detection_language="de"), "PERSON")
        assert any("Hans Müller" in m.text for m in matches)

    def test_firmato_da_it(self):
        text = "Firmato da: Giuseppe Rossi"
        matches = _of_type(detect_regex(text, detection_language="it"), "PERSON")
        assert any("Giuseppe Rossi" in m.text for m in matches)


class TestNotary:
    """Notary name detection."""

    def test_notaire(self):
        text = "Notaire: Maître François Lefèvre"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Lefèvre" in m.text for m in matches)

    def test_notar(self):
        text = "Notar: Dr. Wolfgang Schneider"
        matches = _of_type(detect_regex(text, detection_language="de"), "PERSON")
        assert any("Schneider" in m.text for m in matches)


class TestWitness:
    """Witness name detection."""

    def test_witness_en(self):
        text = "Witness: Sarah Johnson"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("Sarah Johnson" in m.text for m in matches)

    def test_temoin_fr(self):
        text = "Témoin: Michel Blanc"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Michel Blanc" in m.text for m in matches)


class TestCompanyRegistration:
    """Company registration number label-value patterns."""

    def test_kvk_nl(self):
        text = "KvK-nummer: 12345678"
        matches = _of_type(detect_regex(text, detection_language="nl"), "CUSTOM")
        assert any("12345678" in m.text for m in matches)

    def test_companies_house_uk(self):
        text = "Company Number: 01234567"
        matches = _of_type(detect_regex(text, detection_language="en"), "CUSTOM")
        assert any("01234567" in m.text for m in matches)

    def test_partita_iva_label(self):
        text = "Partita IVA: IT12345678901"
        matches = _of_type(detect_regex(text, detection_language="it"), "CUSTOM")
        assert len(matches) >= 1


class TestBankAccountLabels:
    """Sort code, routing number, and account number label patterns."""

    def test_sort_code(self):
        text = "Sort Code: 12-34-56"
        matches = _of_type(detect_regex(text, detection_language="en"), "IBAN")
        assert any("12-34-56" in m.text for m in matches)

    def test_account_number(self):
        text = "Account Number: 12345678"
        matches = _of_type(detect_regex(text), "IBAN")
        assert any("12345678" in m.text for m in matches)

    def test_kontonummer(self):
        text = "Kontonummer: 1234567890"
        matches = _of_type(detect_regex(text, detection_language="de"), "IBAN")
        assert any("1234567890" in m.text for m in matches)


class TestPowerOfAttorney:
    """Power of attorney / representative label patterns."""

    def test_poa_en(self):
        text = "Attorney-in-Fact: Robert James Williams"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("Robert James Williams" in m.text for m in matches)

    def test_mandataire_fr(self):
        text = "Mandataire: Sophie Martin"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Sophie Martin" in m.text for m in matches)


# ═══════════════════════════════════════════════════════════════════════════
# Financial-domain patterns
# ═══════════════════════════════════════════════════════════════════════════


class TestUKSortCodeAccount:
    """UK sort code + account number standalone pattern."""

    def test_sort_code_plus_account(self):
        text = "Payment to 12-34-56 12345678"
        matches = _of_type(detect_regex(text, detection_language="en"), "IBAN")
        assert any("12-34-56 12345678" in m.text for m in matches)


class TestInsurancePolicy:
    """Insurance policy number label-value patterns."""

    def test_policy_en(self):
        text = "Policy Number: POL123456789"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("POL123456789" in m.text for m in matches)

    def test_police_fr(self):
        text = "Police d'assurance n°: ASS987654321"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert any("ASS987654321" in m.text for m in matches)


class TestBeneficiary:
    """Beneficiary / payee label-value patterns."""

    def test_beneficiary_en(self):
        text = "Beneficiary: Alice Marie Johnson"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("Alice Marie Johnson" in m.text for m in matches)

    def test_beneficiaire_fr(self):
        text = "Bénéficiaire: Pierre Durand"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Pierre Durand" in m.text for m in matches)


# ═══════════════════════════════════════════════════════════════════════════
# Patient / medical-domain patterns
# ═══════════════════════════════════════════════════════════════════════════


class TestNHSNumber:
    """UK NHS number detection."""

    def test_nhs_label(self):
        text = "NHS Number: 943 476 5919"
        matches = _of_type(detect_regex(text, detection_language="en"), "SSN")
        assert any("943 476 5919" in m.text for m in matches)

    def test_nhs_validation(self):
        """NHS with valid check digit — should NOT be rejected."""
        from core.detection.regex_detector import _is_valid_nhs_number
        # 943 476 5919 → check last digit
        assert _is_valid_nhs_number("9434765919")


class TestGermanHealthInsurance:
    """German Krankenversichertennummer detection."""

    def test_kvnr_label(self):
        text = "Krankenversichertennummer: A123456789"
        matches = _of_type(detect_regex(text, detection_language="de"), "SSN")
        assert any("A123456789" in m.text for m in matches)

    def test_kvnr_standalone(self):
        text = "Versicherten-Nr: T987654321"
        matches = _of_type(detect_regex(text, detection_language="de"), "SSN")
        assert any("T987654321" in m.text for m in matches)


class TestMedicalRecordNumber:
    """Medical record number / dossier patterns."""

    def test_mrn_en(self):
        text = "MRN: 12345678"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("12345678" in m.text for m in matches)

    def test_dossier_medical_fr(self):
        text = "Dossier médical n°: PAT2024001"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert any("PAT2024001" in m.text for m in matches)

    def test_patientenakte_de(self):
        text = "Patientennummer: P-00012345"
        matches = _of_type(detect_regex(text, detection_language="de"), "CUSTOM")
        assert any("P-00012345" in m.text for m in matches)

    def test_cartella_it(self):
        text = "N° cartella: CC2024-7890"
        matches = _of_type(detect_regex(text, detection_language="it"), "CUSTOM")
        assert any("CC2024-7890" in m.text for m in matches)


class TestDoctorNames:
    """Doctor / physician name detection."""

    def test_physician_en(self):
        text = "Physician: Dr. James Wilson"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("James Wilson" in m.text for m in matches)

    def test_medecin_fr(self):
        text = "Médecin traitant: Dr. Marie Lefebvre"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Marie Lefebvre" in m.text for m in matches)

    def test_arzt_de(self):
        text = "Behandelnder Arzt: Dr. Thomas Schneider"
        matches = _of_type(detect_regex(text, detection_language="de"), "PERSON")
        assert any("Thomas Schneider" in m.text for m in matches)


class TestHospitalNames:
    """Hospital / clinic name detection."""

    def test_hospital_en(self):
        text = "Hospital: Saint Mary General"
        matches = _of_type(detect_regex(text), "ORG")
        assert any("Saint Mary" in m.text for m in matches)

    def test_hopital_fr(self):
        text = "Hôpital: Pitié Salpêtrière"
        matches = _of_type(detect_regex(text, detection_language="fr"), "ORG")
        assert any("Pitié" in m.text or "Salpêtrière" in m.text for m in matches)

    def test_krankenhaus_de(self):
        text = "Krankenhaus: Universitätsklinikum München"
        matches = _of_type(detect_regex(text, detection_language="de"), "ORG")
        assert len(matches) >= 1


class TestHealthInsuranceLabel:
    """Health insurance number label-value patterns."""

    def test_health_insurance_en(self):
        text = "Health Insurance: ABC123456789"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("ABC123456789" in m.text for m in matches)

    def test_carte_vitale_fr(self):
        text = "Carte Vitale: 1850578006084"
        matches = _of_type(detect_regex(text, detection_language="fr"), "CUSTOM")
        assert len(matches) >= 1

    def test_krankenkasse_de(self):
        text = "Krankenkassennummer: T0012345678"
        matches = _of_type(detect_regex(text, detection_language="de"), "CUSTOM")
        assert any("T0012345678" in m.text for m in matches)


class TestEmergencyContact:
    """Emergency contact label-value patterns."""

    def test_emergency_en(self):
        text = "Emergency Contact: Jane Elizabeth Smith"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("Jane Elizabeth Smith" in m.text for m in matches)

    def test_urgence_fr(self):
        text = "Contact d'urgence: Michel Dupont"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Michel Dupont" in m.text for m in matches)

    def test_notfallkontakt_de(self):
        text = "Notfallkontakt: Anna Müller"
        matches = _of_type(detect_regex(text, detection_language="de"), "PERSON")
        assert any("Anna Müller" in m.text for m in matches)


class TestPortugueseNISS:
    """Portuguese NISS label-value patterns."""

    def test_niss_label(self):
        # Use a NISS number that passes the check-digit validation
        text = "NISS: 12345678903"
        matches = _of_type(detect_regex(text, detection_language="es"), "SSN")
        assert any("12345678903" in m.text for m in matches)


class TestBrazilianCPF:
    """Brazilian CPF/CNPJ label-value patterns."""

    def test_cpf_label(self):
        text = "CPF: 123.456.789-09"
        matches = _of_type(detect_regex(text, detection_language="es"), "SSN")
        assert any("123.456.789-09" in m.text for m in matches)

    def test_cnpj_label(self):
        text = "CNPJ: 12.345.678/0001-95"
        matches = _of_type(detect_regex(text, detection_language="es"), "CUSTOM")
        assert any("12.345.678/0001-95" in m.text for m in matches)


class TestItalianCartaIdentita:
    """Italian Carta d'Identità detection."""

    def test_carta_identita(self):
        text = "Carta d'identità: CA12345AA"
        matches = _of_type(detect_regex(text, detection_language="it"), "SSN")
        assert any("CA12345AA" in m.text for m in matches)


class TestGuarantor:
    """Guarantor / surety name detection."""

    def test_guarantor_en(self):
        text = "Guarantor: William Robert Davis"
        matches = _of_type(detect_regex(text), "PERSON")
        assert any("William Robert Davis" in m.text for m in matches)

    def test_garant_fr(self):
        text = "Caution: Philippe Lambert"
        matches = _of_type(detect_regex(text, detection_language="fr"), "PERSON")
        assert any("Philippe Lambert" in m.text for m in matches)


class TestMRNStandalone:
    """Standalone MRN/PAT/DOS pattern."""

    def test_mrn_prefix(self):
        text = "Please refer to MRN-A12345678"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert any("MRN-A12345678" in m.text for m in matches)

    def test_dos_prefix(self):
        text = "Voir DOS: PAT2024001"
        matches = _of_type(detect_regex(text), "CUSTOM")
        assert len(matches) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Validation function unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNHSValidation:
    def test_valid_nhs(self):
        from core.detection.regex_detector import _is_valid_nhs_number
        # Known valid: 4505577104 (example from NHS spec)
        assert _is_valid_nhs_number("4505577104")

    def test_invalid_nhs(self):
        from core.detection.regex_detector import _is_valid_nhs_number
        assert not _is_valid_nhs_number("1234567890")


class TestBICValidation:
    def test_valid_bic(self):
        from core.detection.regex_detector import _is_valid_bic
        assert _is_valid_bic("BNPAFRPP")
        assert _is_valid_bic("DEUTDEFF500")

    def test_invalid_bic_bad_country(self):
        from core.detection.regex_detector import _is_valid_bic
        assert not _is_valid_bic("ABCDXX2L")


class TestItalianPIVAValidation:
    def test_valid_piva(self):
        from core.detection.regex_detector import _is_valid_italian_piva
        # Example valid P.IVA: 07643520567
        assert _is_valid_italian_piva("07643520567")

    def test_invalid_piva(self):
        from core.detection.regex_detector import _is_valid_italian_piva
        assert not _is_valid_italian_piva("00000000001")

