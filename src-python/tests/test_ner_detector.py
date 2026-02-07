"""Tests for the NER (spaCy) PII detector."""

import pytest

from core.detection.ner_detector import detect_ner, _nlp
from models.schemas import PIIType


class TestNERDetector:
    def test_person_detection(self):
        results = detect_ner("Barack Obama visited Paris last Tuesday.")
        names = [r for r in results if r.pii_type == PIIType.PERSON]
        assert len(names) >= 1
        assert any("Obama" in r.text for r in names)

    def test_location_detection(self):
        results = detect_ner("The meeting is in New York City at 3pm.")
        locs = [r for r in results if r.pii_type == PIIType.LOCATION]
        assert len(locs) >= 1

    def test_organization_detection(self):
        results = detect_ner("She works at Google and previously at Microsoft.")
        orgs = [r for r in results if r.pii_type == PIIType.ORG]
        assert len(orgs) >= 1

    def test_empty_text(self):
        results = detect_ner("")
        assert results == []

    def test_no_entities(self):
        results = detect_ner("The quick brown fox jumps over the lazy dog.")
        # spaCy may or may not find entities here; just ensure no crash
        assert isinstance(results, list)
