"""Tests for the LLM-based PII detector — unit-level (no real LLM needed)."""

from __future__ import annotations

import pytest
from core.detection.llm_detector import (
    LLMMatch,
    _fuzzy_find,
    _parse_llm_response,
    _deduplicate,
    detect_llm,
)
from models.schemas import PIIType


# ── _fuzzy_find ──────────────────────────────────────────────────────────

class TestFuzzyFind:
    def test_exact_match(self):
        assert _fuzzy_find("hello", "say hello world") == 4

    def test_case_insensitive(self):
        assert _fuzzy_find("HELLO", "say hello world") == 4

    def test_no_match(self):
        assert _fuzzy_find("zzzzz", "say hello world") is None

    def test_empty_needle(self):
        assert _fuzzy_find("", "hello") is None or _fuzzy_find("", "hello") == 0

    def test_fuzzy_close_match(self):
        # SequenceMatcher should handle a minor typo
        idx = _fuzzy_find("Jhon Smith", "Contact John Smith at this address")
        assert idx is not None
        assert idx == 8  # "John Smith" starts at index 8


# ── _parse_llm_response ─────────────────────────────────────────────────

class TestParseLLMResponse:
    def test_valid_json(self):
        response = '[{"text": "John", "type": "PERSON", "reason": "name"}]'
        source = "Contact John at the office"
        matches = _parse_llm_response(response, source, 0)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.PERSON
        assert matches[0].text == "John"

    def test_empty_array(self):
        matches = _parse_llm_response("[]", "some text", 0)
        assert matches == []

    def test_invalid_json(self):
        matches = _parse_llm_response("not json at all", "text", 0)
        assert matches == []

    def test_markdown_code_block(self):
        response = '```json\n[{"text": "Alice", "type": "PERSON", "reason": "name"}]\n```'
        matches = _parse_llm_response(response, "Alice works here", 0)
        assert len(matches) == 1
        assert matches[0].text == "Alice"

    def test_unknown_type_defaults_to_custom(self):
        response = '[{"text": "XYZ-123", "type": "UNKNOWN_TYPE", "reason": "?"}]'
        matches = _parse_llm_response(response, "ID is XYZ-123 here", 0)
        assert len(matches) == 1
        assert matches[0].pii_type == PIIType.CUSTOM

    def test_global_offset_applied(self):
        response = '[{"text": "Alice", "type": "PERSON", "reason": "name"}]'
        matches = _parse_llm_response(response, "Alice works here", global_offset=100)
        assert len(matches) == 1
        assert matches[0].start == 100
        assert matches[0].end == 105

    def test_text_not_found_skipped(self):
        response = '[{"text": "ZZZNOTFOUND", "type": "PERSON", "reason": "?"}]'
        matches = _parse_llm_response(response, "Alice works here", 0)
        assert matches == []


# ── _deduplicate ─────────────────────────────────────────────────────────

class TestDeduplicate:
    def test_no_duplicates(self):
        matches = [
            LLMMatch(0, 5, "Alice", PIIType.PERSON, 0.75),
            LLMMatch(10, 15, "Bob", PIIType.PERSON, 0.75),
        ]
        result = _deduplicate(matches)
        assert len(result) == 2

    def test_overlapping_keeps_better(self):
        matches = [
            LLMMatch(0, 5, "Alice", PIIType.PERSON, 0.75),
            LLMMatch(3, 10, "ce Smith", PIIType.PERSON, 0.85),
        ]
        result = _deduplicate(matches)
        assert len(result) == 1
        assert result[0].confidence == 0.85

    def test_empty(self):
        assert _deduplicate([]) == []

    def test_identical_matches(self):
        m = LLMMatch(0, 5, "Alice", PIIType.PERSON, 0.75)
        result = _deduplicate([m, m])
        assert len(result) == 1


# ── detect_llm (integration-level with mock engine) ──────────────────────

class _MockLLMEngine:
    """Minimal mock that responds with a fixed JSON array."""

    def __init__(self, response: str = "[]"):
        self._response = response

    def is_loaded(self) -> bool:
        return True

    def generate(self, **kwargs) -> str:
        return self._response


class TestDetectLLM:
    def test_empty_text(self):
        engine = _MockLLMEngine()
        assert detect_llm("", engine) == []

    def test_short_text_skipped(self):
        engine = _MockLLMEngine()
        assert detect_llm("hi", engine) == []

    def test_none_engine(self):
        assert detect_llm("long enough text to pass minimum length check easily", None) == []

    def test_engine_returns_empty(self):
        engine = _MockLLMEngine("[]")
        result = detect_llm("x" * 100, engine)
        assert result == []

    def test_engine_returns_match(self):
        text = "Please contact John Smith at the headquarters for more information about this."
        response = '[{"text": "John Smith", "type": "PERSON", "reason": "name"}]'
        engine = _MockLLMEngine(response)
        result = detect_llm(text, engine)
        assert len(result) == 1
        assert result[0].pii_type == PIIType.PERSON
        assert result[0].text == "John Smith"
