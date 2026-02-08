"""Tests for the regex PII detector."""

from core.detection.regex_detector import detect_regex


class TestRegexDetector:
    """Validate built-in regex patterns for common PII types."""

    def test_ssn_detection(self):
        text = "My SSN is 123-45-6789, please keep it private."
        matches = detect_regex(text)
        ssn_matches = [m for m in matches if m.pii_type == "SSN"]
        assert len(ssn_matches) == 1
        assert text[ssn_matches[0].start : ssn_matches[0].end] == "123-45-6789"

    def test_email_detection(self):
        text = "Contact me at john.doe@example.com for details."
        matches = detect_regex(text)
        email_matches = [m for m in matches if m.pii_type == "EMAIL"]
        assert len(email_matches) == 1
        assert "john.doe@example.com" in text[email_matches[0].start : email_matches[0].end]

    def test_phone_detection(self):
        text = "Call me at (555) 123-4567 or +1-555-987-6543."
        matches = detect_regex(text)
        phone_matches = [m for m in matches if m.pii_type == "PHONE"]
        assert len(phone_matches) >= 1

    def test_credit_card_detection(self):
        text = "My card number is 4111 1111 1111 1111."
        matches = detect_regex(text)
        cc_matches = [m for m in matches if m.pii_type == "CREDIT_CARD"]
        assert len(cc_matches) == 1

    def test_ip_address_detection(self):
        text = "Server IP is 192.168.1.100 and secondary is 10.0.0.1."
        matches = detect_regex(text)
        ip_matches = [m for m in matches if m.pii_type == "IP_ADDRESS"]
        assert len(ip_matches) == 2

    def test_no_false_positives_on_clean_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        matches = detect_regex(text)
        assert len(matches) == 0

    def test_multiple_pii_types(self):
        text = "Name: John, SSN: 123-45-6789, email: john@test.com"
        matches = detect_regex(text)
        types = {m.pii_type for m in matches}
        assert "SSN" in types
        assert "EMAIL" in types

    def test_iban_detection(self):
        # IBAN regex removed (too many FPs on financial docs).
        # Now we just verify it does NOT match.
        text = "Wire to IBAN DE89370400440532013000 please."
        matches = detect_regex(text)
        iban_matches = [m for m in matches if getattr(m.pii_type, 'value', m.pii_type) == "IBAN"]
        assert len(iban_matches) == 0
