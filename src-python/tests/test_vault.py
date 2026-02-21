"""Tests for the token vault (plaintext store, retrieve, resolve)."""

import tempfile
from pathlib import Path

import pytest

from core.vault.store import TokenVault
from models.schemas import PIIType, TokenMapping


def _store(vault: TokenVault, original_text: str, pii_type: PIIType,
           source_document: str = "") -> TokenMapping:
    """Helper: create a TokenMapping, store it, and return it."""
    token_string = vault.generate_token_string(pii_type)
    mapping = TokenMapping(
        token_string=token_string,
        original_text=original_text,
        pii_type=pii_type,
        source_document=source_document,
    )
    vault.store_token(mapping)
    return mapping


@pytest.fixture
def vault(tmp_path: Path):
    """Create a temporary vault for each test."""
    db_path = tmp_path / "test_vault.db"
    v = TokenVault(db_path=db_path)
    v.initialize()
    return v


class TestTokenVault:
    def test_initialize_and_unlock(self, vault: TokenVault):
        assert vault.is_unlocked is True

    def test_store_and_resolve_token(self, vault: TokenVault):
        m = _store(vault, "John Doe", PIIType.PERSON, "doc-001")
        assert m.token_string.startswith("[P")
        assert m.token_string.endswith("]")
        assert len(m.token_string) == 8  # [P38291]

        resolved = vault.resolve_token(m.token_string)
        assert resolved is not None
        assert resolved.original_text == "John Doe"
        assert resolved.pii_type == PIIType.PERSON

    def test_resolve_unknown_token(self, vault: TokenVault):
        result = vault.resolve_token("[P99999]")
        assert result is None

    def test_resolve_all_in_text(self, vault: TokenVault):
        m1 = _store(vault, "Alice", PIIType.PERSON, "doc-001")
        m2 = _store(vault, "secret@mail.com", PIIType.EMAIL, "doc-001")

        text_with_tokens = f"Dear {m1.token_string}, your email {m2.token_string} has been logged."
        resolved_text, count, unresolved = vault.resolve_all_tokens(text_with_tokens)

        assert count == 2
        assert "Alice" in resolved_text
        assert "secret@mail.com" in resolved_text
        assert "[P" not in resolved_text
        assert "[E" not in resolved_text

    def test_list_tokens(self, vault: TokenVault):
        _store(vault, "Bob", PIIType.PERSON, "doc-002")
        _store(vault, "123-45-6789", PIIType.SSN, "doc-002")

        tokens = vault.list_tokens()
        assert len(tokens) == 2

    def test_delete_token(self, vault: TokenVault):
        m = _store(vault, "Carol", PIIType.PERSON, "doc-003")
        assert vault.resolve_token(m.token_string) is not None

        vault.delete_token(m.token_id)
        assert vault.resolve_token(m.token_string) is None

    def test_get_stats(self, vault: TokenVault):
        _store(vault, "Dave", PIIType.PERSON, "doc-004")
        _store(vault, "dave@x.com", PIIType.EMAIL, "doc-004")
        _store(vault, "555-1234", PIIType.PHONE, "doc-004")

        stats = vault.get_stats()
        assert stats["total_tokens"] == 3

    def test_register_document(self, vault: TokenVault):
        vault.register_document("doc-005", "report.pdf", 3)
        # Should not raise on duplicate
        vault.register_document("doc-005", "report.pdf", 3)
