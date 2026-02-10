"""Tests for core/detokenize_file.py — text/CSV de-tokenization path.

The TXT path exercises vault.resolve_all_tokens without needing fitz, docx
or openpyxl, keeping the test lightweight.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Optional

import pytest

# detokenize_file imports fitz at module level; skip entire module when missing
fitz = pytest.importorskip("fitz", reason="PyMuPDF (fitz) not installed")

from core.vault.store import TokenVault
from models.schemas import PIIType, TokenMapping


@pytest.fixture
def vault(tmp_path: Path) -> TokenVault:
    """Create a temporary vault pre-loaded with two tokens."""
    v = TokenVault(db_path=tmp_path / "test.db")
    v.initialize("pass-for-test")
    return v


def _store(vault: TokenVault, text: str, pii_type: PIIType) -> TokenMapping:
    token_string = vault.generate_token_string(pii_type)
    mapping = TokenMapping(
        token_string=token_string,
        original_text=text,
        pii_type=pii_type,
    )
    vault.store_token(mapping)
    return mapping


class TestDetokenizeTxt:
    """Test the plain-text / CSV path of detokenize_file."""

    def test_txt_round_trip(self, vault: TokenVault):
        from core.detokenize_file import detokenize_file

        m1 = _store(vault, "Alice", PIIType.PERSON)
        m2 = _store(vault, "alice@x.com", PIIType.EMAIL)

        txt = f"Hello {m1.token_string}, your email is {m2.token_string}.".encode()
        out_bytes, out_name, count, unresolved = detokenize_file(txt, "doc.txt", vault)

        assert count == 2
        assert len(unresolved) == 0
        result = out_bytes.decode("utf-8")
        assert "Alice" in result
        assert "alice@x.com" in result
        assert "[ANON_" not in result
        assert out_name.endswith(".txt")

    def test_csv_round_trip(self, vault: TokenVault):
        from core.detokenize_file import detokenize_file

        m = _store(vault, "Bob", PIIType.PERSON)
        csv = f"name,city\n{m.token_string},NYC\n".encode()
        out_bytes, out_name, count, unresolved = detokenize_file(csv, "data.csv", vault)

        assert count == 1
        assert "Bob" in out_bytes.decode("utf-8")
        assert out_name.endswith(".csv")

    def test_no_tokens(self, vault: TokenVault):
        from core.detokenize_file import detokenize_file

        txt = b"No tokens at all."
        out_bytes, out_name, count, unresolved = detokenize_file(txt, "plain.txt", vault)

        assert count == 0
        assert out_bytes == txt

    def test_unresolved_token(self, vault: TokenVault):
        from core.detokenize_file import detokenize_file

        txt = b"Value is [ANON_PERSON_DEADBE], ok?"
        out_bytes, out_name, count, unresolved = detokenize_file(txt, "x.txt", vault)

        # Token isn't in vault → unresolved
        assert count == 0
        assert len(unresolved) == 1 or "[ANON_PERSON_DEADBE]" in out_bytes.decode()

    def test_unsupported_extension(self, vault: TokenVault):
        from core.detokenize_file import detokenize_file

        with pytest.raises(ValueError, match="(?i)unsupported|not supported"):
            detokenize_file(b"binary", "image.bmp", vault)
