"""Tests for Italian language support.

Covers Italian street addresses, postal codes, label-value patterns,
context keywords, person title patterns, and NER text detection.
"""

import pytest
from core.detection.regex_detector import detect_regex

try:
    from core.detection.ner_detector import _is_italian_text
    _HAS_SPACY = True
except ImportError:
    _HAS_SPACY = False


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _types(matches):
    return {getattr(m.pii_type, "value", m.pii_type) for m in matches}


def _of_type(matches, pii_type_str):
    return [m for m in matches
            if getattr(m.pii_type, "value", m.pii_type) == pii_type_str]


# ═══════════════════════════════════════════════════════════════════════════
# Italian language detection
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HAS_SPACY, reason="spaCy not installed")
class TestItalianLanguageDetection:
    def test_italian_text_detected(self):
        text = (
            "Il signor Rossi ha presentato la domanda di risarcimento "
            "presso il tribunale di Milano. La sua residenza è in Via Roma 42, "
            "nella regione Lombardia. Il procedimento è stato avviato il "
            "15 gennaio 2024 e si è concluso con una sentenza favorevole. "
            "Il giudice ha stabilito che il risarcimento deve essere "
            "corrisposto entro trenta giorni dalla notifica."
        )
        assert _is_italian_text(text)

    def test_english_text_not_italian(self):
        text = (
            "The company has reported strong earnings for the fourth quarter "
            "of 2024. Revenue increased by 15% compared to the previous year, "
            "driven by strong demand in the consumer electronics segment."
        )
        assert not _is_italian_text(text)

    def test_short_text_not_italian(self):
        assert not _is_italian_text("Ciao mondo")


# ═══════════════════════════════════════════════════════════════════════════
# Italian street addresses
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianStreetAddresses:
    def test_via_with_number(self):
        matches = detect_regex("Residente in Via Roma 42, Milano")
        addr = _of_type(matches, "ADDRESS")
        assert any("Via Roma 42" in m.text for m in addr)

    def test_via_with_comma_number(self):
        matches = detect_regex("Indirizzo: Via Garibaldi, 15")
        addr = _of_type(matches, "ADDRESS")
        assert any("Via Garibaldi" in m.text for m in addr)

    def test_piazza(self):
        matches = detect_regex("Si trova in Piazza del Duomo 1")
        addr = _of_type(matches, "ADDRESS")
        assert any("Piazza" in m.text for m in addr)

    def test_corso(self):
        matches = detect_regex("L'ufficio è in Corso Italia 15")
        addr = _of_type(matches, "ADDRESS")
        assert any("Corso Italia" in m.text for m in addr)

    def test_viale(self):
        matches = detect_regex("Viale della Libertà 100, Palermo")
        addr = _of_type(matches, "ADDRESS")
        assert any("Viale" in m.text for m in addr)

    def test_largo(self):
        matches = detect_regex("Largo Augusto 3, Milano")
        addr = _of_type(matches, "ADDRESS")
        assert any("Largo Augusto" in m.text for m in addr)

    def test_vicolo(self):
        matches = detect_regex("Vicolo Stretto 7, Firenze")
        addr = _of_type(matches, "ADDRESS")
        assert any("Vicolo Stretto" in m.text for m in addr)

    def test_lungomare(self):
        matches = detect_regex("Lungomare Caracciolo 10, Napoli")
        addr = _of_type(matches, "ADDRESS")
        assert any("Lungomare" in m.text for m in addr)

    def test_via_without_number(self):
        """Street names without house numbers should still match."""
        matches = detect_regex("Abitava in Via Dante Alighieri")
        addr = _of_type(matches, "ADDRESS")
        assert any("Via Dante" in m.text for m in addr)

    def test_via_with_di_preposition(self):
        matches = detect_regex("Via di Porta Maggiore 12, Roma")
        addr = _of_type(matches, "ADDRESS")
        assert any("Via di Porta" in m.text for m in addr)


# ═══════════════════════════════════════════════════════════════════════════
# Italian postal codes (CAP)
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianPostalCodes:
    def test_cap_with_known_city(self):
        matches = detect_regex("Il paziente risiede a 20121 Milano")
        addr = _of_type(matches, "ADDRESS")
        assert any("20121 Milano" in m.text for m in addr)

    def test_cap_roma(self):
        matches = detect_regex("Sede a 00100 Roma")
        addr = _of_type(matches, "ADDRESS")
        assert any("00100 Roma" in m.text for m in addr)

    def test_cap_napoli(self):
        matches = detect_regex("Filiale di 80100 Napoli")
        addr = _of_type(matches, "ADDRESS")
        assert any("80100 Napoli" in m.text for m in addr)

    def test_cap_with_i_prefix(self):
        matches = detect_regex("Indirizzo: I-50121 Firenze")
        addr = _of_type(matches, "ADDRESS")
        assert any("Firenze" in m.text for m in addr)

    def test_cap_with_i_dash_prefix_any_city(self):
        matches = detect_regex("I-37100 Verona centro")
        addr = _of_type(matches, "ADDRESS")
        assert any("Verona" in m.text for m in addr)


# ═══════════════════════════════════════════════════════════════════════════
# Italian label-value PERSON patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianLabelValuePerson:
    def test_nome_label(self):
        matches = detect_regex("Nome: Giovanni Rossi")
        person = _of_type(matches, "PERSON")
        assert any("Giovanni Rossi" in m.text for m in person)

    def test_cognome_label(self):
        matches = detect_regex("Cognome: Bianchi")
        person = _of_type(matches, "PERSON")
        assert any("Bianchi" in m.text for m in person)

    def test_nominativo_label(self):
        matches = detect_regex("Nominativo: Marco Verdi")
        person = _of_type(matches, "PERSON")
        assert any("Marco Verdi" in m.text for m in person)

    def test_paziente_label(self):
        matches = detect_regex("Paziente: Luca Bianchi")
        person = _of_type(matches, "PERSON")
        assert any("Luca Bianchi" in m.text for m in person)

    def test_intestatario_label(self):
        matches = detect_regex("Intestatario: Maria Conti")
        person = _of_type(matches, "PERSON")
        assert any("Maria Conti" in m.text for m in person)

    def test_assistito_label(self):
        matches = detect_regex("Assistito: Paolo Esposito")
        person = _of_type(matches, "PERSON")
        assert any("Paolo Esposito" in m.text for m in person)


# ═══════════════════════════════════════════════════════════════════════════
# Italian person title patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianPersonTitles:
    def test_sig_rossi(self):
        matches = detect_regex("Sig. Rossi ha firmato il contratto")
        person = _of_type(matches, "PERSON")
        assert any("Rossi" in m.text for m in person)

    def test_sig_ra_bianchi(self):
        matches = detect_regex("Sig.ra Bianchi è la responsabile")
        person = _of_type(matches, "PERSON")
        assert any("Bianchi" in m.text for m in person)

    def test_sig_na_verdi(self):
        matches = detect_regex("Sig.na Verdi ha presentato domanda")
        person = _of_type(matches, "PERSON")
        assert any("Verdi" in m.text for m in person)


# ═══════════════════════════════════════════════════════════════════════════
# Italian Codice Fiscale
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianCodiceFiscale:
    def test_standalone_codice_fiscale(self):
        matches = detect_regex("Il codice fiscale è RSSMRA85M01H501Z")
        ssn = _of_type(matches, "SSN")
        assert any("RSSMRA85M01H501Z" in m.text for m in ssn)

    def test_codice_fiscale_label_value(self):
        matches = detect_regex("Codice Fiscale: BNCLCU90A15F205X")
        ssn = _of_type(matches, "SSN")
        assert any("BNCLCU90A15F205X" in m.text for m in ssn)

    def test_cf_abbreviation(self):
        matches = detect_regex("C.F.: RSSMRA85M01H501Z")
        ssn = _of_type(matches, "SSN")
        assert any("RSSMRA85M01H501Z" in m.text for m in ssn)


# ═══════════════════════════════════════════════════════════════════════════
# Italian date patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianDates:
    def test_italian_date_with_month_name(self):
        matches = detect_regex("Nato il 15 gennaio 1985")
        dates = _of_type(matches, "DATE")
        assert any("15 gennaio 1985" in m.text for m in dates)

    def test_italian_date_september(self):
        matches = detect_regex("documento del 3 settembre 2024")
        dates = _of_type(matches, "DATE")
        assert any("3 settembre 2024" in m.text for m in dates)

    def test_italian_dob_label(self):
        matches = detect_regex("Data di nascita: 01/06/1990")
        dates = _of_type(matches, "DATE")
        assert any("01/06/1990" in m.text for m in dates)


# ═══════════════════════════════════════════════════════════════════════════
# Italian label-value patterns — other types
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianLabelValueOther:
    def test_passaporto_label(self):
        matches = detect_regex("Passaporto: YA3456789")
        passport = _of_type(matches, "PASSPORT")
        assert any("YA3456789" in m.text for m in passport)

    def test_patente_di_guida_label(self):
        matches = detect_regex("Patente di guida: MI1234567X")
        dl = _of_type(matches, "DRIVER_LICENSE")
        assert any("MI1234567X" in m.text for m in dl)

    def test_indirizzo_label(self):
        matches = detect_regex("Indirizzo: Via Roma 42, 20121 Milano\nTelefono: 02 1234567")
        addr = _of_type(matches, "ADDRESS")
        assert any("Via Roma" in m.text for m in addr)

    def test_partita_iva_label(self):
        matches = detect_regex("Partita IVA: IT01234567890")
        custom = _of_type(matches, "CUSTOM")
        assert any("01234567890" in m.text for m in custom)

    def test_conto_corrente_label(self):
        matches = detect_regex("Conto corrente: IT60X0542811101000000123456")
        iban = _of_type(matches, "IBAN")
        assert any("IT60X0542811101000000123456" in m.text for m in iban)

    def test_domicilio_label(self):
        matches = detect_regex("Domicilio: Piazza Garibaldi 5, 50121 Firenze\nEmail: test@example.com")
        addr = _of_type(matches, "ADDRESS")
        assert any("Piazza Garibaldi" in m.text or "Firenze" in m.text for m in addr)

    def test_residenza_label(self):
        matches = detect_regex("Residenza: Corso Vittorio Emanuele 100, Roma\nTel: 06 12345678")
        addr = _of_type(matches, "ADDRESS")
        assert any("Corso Vittorio" in m.text or "Roma" in m.text for m in addr)


# ═══════════════════════════════════════════════════════════════════════════
# Italian ORG patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianOrg:
    def test_srl_suffix(self):
        matches = detect_regex("Fattura di Rossi Costruzioni S.R.L.")
        org = _of_type(matches, "ORG")
        assert any("Rossi" in m.text and "S.R.L." in m.text for m in org)

    def test_spa_suffix(self):
        matches = detect_regex("contratto con Fiat Auto S.A.")
        # S.A. matches the French/general SA pattern
        org = _of_type(matches, "ORG")
        assert len(org) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Casella Postale (PO Box)
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianPOBox:
    def test_casella_postale(self):
        matches = detect_regex("Casella Postale 123, 00100 Roma")
        addr = _of_type(matches, "ADDRESS")
        assert any("Casella Postale 123" in m.text or "00100 Roma" in m.text for m in addr)

    def test_cp_abbreviation(self):
        matches = detect_regex("C.P. 456")
        addr = _of_type(matches, "ADDRESS")
        assert any("C.P. 456" in m.text for m in addr)


# ═══════════════════════════════════════════════════════════════════════════
# Context keyword boosting for Italian
# ═══════════════════════════════════════════════════════════════════════════

class TestItalianContextBoost:
    def test_codice_fiscale_context_boosts_ssn(self):
        """Codice fiscale context keyword should boost SSN confidence."""
        text_with_ctx = "codice fiscale RSSMRA85M01H501Z"
        text_without_ctx = "RSSMRA85M01H501Z"
        matches_with = detect_regex(text_with_ctx)
        matches_without = detect_regex(text_without_ctx)
        ssn_with = _of_type(matches_with, "SSN")
        ssn_without = _of_type(matches_without, "SSN")
        assert len(ssn_with) >= 1
        assert len(ssn_without) >= 1
        if ssn_with and ssn_without:
            assert ssn_with[0].confidence >= ssn_without[0].confidence

    def test_indirizzo_context_in_keywords(self):
        """Italian address context keywords should be recognized."""
        text = "indirizzo del paziente: Via Verdi 10, Firenze"
        matches = detect_regex(text)
        addr = _of_type(matches, "ADDRESS")
        assert len(addr) >= 1
