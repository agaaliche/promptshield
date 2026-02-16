"""Tests for the language detection module."""

import pytest

from core.detection.language import (
    detect_language,
    resolve_auto_model,
    SUPPORTED_LANGUAGES,
    AUTO_MODEL_ENGLISH,
    AUTO_MODEL_MULTILINGUAL,
)


# ── detect_language ──────────────────────────────────────────────────────

class TestDetectLanguage:
    """Verify that stop-word-based language detection identifies each of
    the 7 supported languages correctly."""

    def test_english(self):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a test sentence with common English words. "
            "We are going to check that the language detector works properly."
        )
        assert detect_language(text) == "en"

    def test_french(self):
        text = (
            "Le chat noir est assis sur le tapis dans la maison. "
            "Il fait très beau aujourd'hui et nous allons au parc. "
            "Les enfants jouent avec leurs amis dans le jardin."
        )
        assert detect_language(text) == "fr"

    def test_german(self):
        text = (
            "Der große Hund liegt auf dem Teppich im Wohnzimmer. "
            "Heute ist ein schöner Tag und wir gehen in den Park. "
            "Die Kinder spielen mit ihren Freunden auf dem Spielplatz."
        )
        assert detect_language(text) == "de"

    def test_spanish(self):
        text = (
            "El gato negro está sentado sobre la alfombra en la casa. "
            "Hoy hace muy buen tiempo y vamos al parque con los niños. "
            "Los amigos están jugando en el jardín esta tarde."
        )
        assert detect_language(text) == "es"

    def test_italian(self):
        text = (
            "Il gatto nero è seduto sul tappeto nella casa. "
            "Oggi fa molto bello e andiamo al parco con gli amici. "
            "I bambini giocano nel giardino questa sera dopo la cena."
        )
        assert detect_language(text) == "it"

    def test_dutch(self):
        text = (
            "De zwarte kat zit op het tapijt in de woonkamer. "
            "Vandaag is het mooi weer en we gaan naar het park. "
            "De kinderen spelen met hun vrienden op het plein."
        )
        assert detect_language(text) == "nl"

    def test_portuguese(self):
        text = (
            "O gato preto está sentado sobre o tapete na casa. "
            "Hoje faz muito bom tempo e vamos ao parque com os amigos. "
            "As crianças estão brincando no jardim depois do jantar."
        )
        assert detect_language(text) == "pt"

    def test_too_short_defaults_to_english(self):
        """Text shorter than the minimum word threshold should default to English."""
        assert detect_language("hello") == "en"
        assert detect_language("") == "en"

    def test_gibberish_defaults_to_english(self):
        """Strings with no stop-word matches default to English."""
        text = "xylophonic zymotic quagga quahog " * 15
        assert detect_language(text) == "en"

    def test_supported_languages_contains_all(self):
        """All 7 language codes should be in SUPPORTED_LANGUAGES."""
        expected = {"en", "fr", "de", "es", "it", "nl", "pt"}
        assert expected == set(SUPPORTED_LANGUAGES)


# ── resolve_auto_model ───────────────────────────────────────────────────

class TestResolveAutoModel:
    def test_english_returns_english_model(self):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "This is a test sentence with common English words that should work."
        )
        model_id, lang = resolve_auto_model(text)
        assert lang == "en"
        assert model_id == AUTO_MODEL_ENGLISH

    def test_non_english_returns_multilingual_model(self):
        text = (
            "Le chat noir est assis sur le tapis dans la maison. "
            "Il fait très beau aujourd'hui et nous allons au parc."
        )
        model_id, lang = resolve_auto_model(text)
        assert lang != "en"
        assert model_id == AUTO_MODEL_MULTILINGUAL
