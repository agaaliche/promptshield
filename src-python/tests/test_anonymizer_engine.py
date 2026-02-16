"""Tests for the anonymizer engine — dispatch, PDF, DOCX, image handlers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.anonymizer.engine import (
    _get_context_snippet,
    _replace_in_paragraphs,
    anonymize_document,
)
from core.vault.store import TokenVault
from models.schemas import (
    AnonymizeResponse,
    BBox,
    DocumentInfo,
    DocumentStatus,
    PageData,
    PIIRegion,
    PIIType,
    RegionAction,
    DetectionSource,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def vault(tmp_path: Path):
    """Temporary vault for each test."""
    db_path = tmp_path / "test_vault.db"
    v = TokenVault(db_path=db_path)
    v.initialize("test-passphrase-unit!")
    return v


@pytest.fixture
def temp_dir(tmp_path: Path):
    """Override config.temp_dir so output goes to tmp."""
    return tmp_path


# ── _get_context_snippet ──────────────────────────────────────────────


class TestGetContextSnippet:
    def test_middle_of_text(self):
        text = "A" * 100 + "John" + "B" * 100
        result = _get_context_snippet(text, 100, 104, context_chars=10)
        assert "John" in result
        assert result.startswith("...")
        assert result.endswith("...")

    def test_start_of_text(self):
        text = "John Doe is here in Paris for a meeting"
        result = _get_context_snippet(text, 0, 8, context_chars=10)
        assert not result.startswith("...")
        assert result.endswith("...")

    def test_end_of_text(self):
        text = "Meeting with John Doe"
        result = _get_context_snippet(text, 13, 21, context_chars=5)
        assert result.startswith("...")
        assert not result.endswith("...")

    def test_short_text(self):
        text = "hello"
        result = _get_context_snippet(text, 0, 5, context_chars=50)
        assert result == "hello"

    def test_empty_text(self):
        result = _get_context_snippet("", 0, 0, context_chars=10)
        assert result == ""


# ── _replace_in_paragraphs ───────────────────────────────────────────


class _FakeRun:
    """Minimal mock of a docx.text.run.Run."""
    def __init__(self, text: str):
        self.text = text
        self.font = None  # just needs to exist


class _FakeParagraph:
    """Minimal mock of a docx.text.paragraph.Paragraph."""
    def __init__(self, run_texts: list[str]):
        self._runs = [_FakeRun(t) for t in run_texts]

    @property
    def runs(self):
        return self._runs


class TestReplaceInParagraphs:
    def test_single_run_replacement(self):
        para = _FakeParagraph(["Hello John Doe, welcome!"])
        _replace_in_paragraphs([para], {"John Doe": "---"})
        assert para.runs[0].text == "Hello ---, welcome!"

    def test_cross_run_replacement(self):
        """PII split across multiple runs should still be replaced."""
        para = _FakeParagraph(["Joh", "n D", "oe"])
        _replace_in_paragraphs([para], {"John Doe": "[TOKEN]"})
        # After replacement, first run holds all text, rest empty
        full = "".join(r.text for r in para.runs)
        assert full == "[TOKEN]"

    def test_no_match_unchanged(self):
        para = _FakeParagraph(["Nothing to replace here"])
        _replace_in_paragraphs([para], {"MISSING": "---"})
        assert para.runs[0].text == "Nothing to replace here"

    def test_empty_paragraph(self):
        para = _FakeParagraph([""])
        _replace_in_paragraphs([para], {"x": "y"})
        assert para.runs[0].text == ""

    def test_no_runs(self):
        para = _FakeParagraph([])
        _replace_in_paragraphs([para], {"x": "y"})
        assert para.runs == []

    def test_multiple_replacements(self):
        para = _FakeParagraph(["John Doe lives in Paris"])
        _replace_in_paragraphs(
            [para],
            {"John Doe": "[PERSON]", "Paris": "[LOC]"},
        )
        assert para.runs[0].text == "[PERSON] lives in [LOC]"

    def test_style_preservation_unrelated_runs_untouched(self):
        """Runs that don't overlap PII must keep their text verbatim,
        which means their formatting (carried by the Run XML element)
        is preserved."""
        # Paragraph: "Dear " (run0, normal) + "John Doe" (run1, bold) + ", welcome!" (run2, normal)
        para = _FakeParagraph(["Dear ", "John Doe", ", welcome!"])
        _replace_in_paragraphs([para], {"John Doe": "[TOKEN]"})
        # run0 and run2 should be unchanged — their styles survive
        assert para.runs[0].text == "Dear "
        assert para.runs[1].text == "[TOKEN]"
        assert para.runs[2].text == ", welcome!"

    def test_cross_run_style_surrounding_runs_intact(self):
        """When PII spans the middle runs, surrounding runs are untouched."""
        # "Intro " | "Joh" | "n D" | "oe" | " end"
        para = _FakeParagraph(["Intro ", "Joh", "n D", "oe", " end"])
        _replace_in_paragraphs([para], {"John Doe": "[TOK]"})
        assert para.runs[0].text == "Intro "
        assert para.runs[4].text == " end"
        full = "".join(r.text for r in para.runs)
        assert full == "Intro [TOK] end"

    def test_partial_run_overlap_preserves_remainder(self):
        """If PII starts mid-run and ends mid-run, the non-PII parts stay."""
        # "Hello John Doe, bye" all in one run
        para = _FakeParagraph(["Hello John Doe, bye"])
        _replace_in_paragraphs([para], {"John Doe": "[T]"})
        assert para.runs[0].text == "Hello [T], bye"


# ── anonymize_document dispatch ──────────────────────────────────────


class TestAnonymizeDocumentDispatch:
    @pytest.mark.asyncio
    async def test_vault_locked_raises(self, tmp_path):
        doc = DocumentInfo(
            original_filename="test.pdf",
            file_path=str(tmp_path / "test.pdf"),
            mime_type="application/pdf",
        )
        # Vault not unlocked → should raise
        with patch("core.anonymizer.engine.vault") as mock_vault:
            mock_vault.is_unlocked = False
            with pytest.raises(RuntimeError, match="Vault must be unlocked"):
                await anonymize_document(doc)

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path):
        doc = DocumentInfo(
            original_filename="missing.pdf",
            file_path=str(tmp_path / "missing.pdf"),
            mime_type="application/pdf",
        )
        with patch("core.anonymizer.engine.vault") as mock_vault:
            mock_vault.is_unlocked = True
            with pytest.raises(RuntimeError, match="Original file not found"):
                await anonymize_document(doc)

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self, tmp_path):
        fp = tmp_path / "test.xyz"
        fp.write_text("dummy")
        doc = DocumentInfo(
            original_filename="test.xyz",
            file_path=str(fp),
            mime_type="application/octet-stream",
        )
        with patch("core.anonymizer.engine.vault") as mock_vault:
            mock_vault.is_unlocked = True
            with pytest.raises(ValueError, match="Unsupported file type"):
                await anonymize_document(doc)


# ── Image anonymization (lightweight — no PyMuPDF dependency) ────────


class TestAnonymizeImage:
    @pytest.mark.asyncio
    async def test_image_remove_region(self, vault: TokenVault, tmp_path: Path):
        """Create a small test image, add a REMOVE region, ensure output exists."""
        from PIL import Image

        # Create a small 200×200 white image
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        img_path = tmp_path / "test.png"
        img.save(str(img_path), "PNG")

        doc = DocumentInfo(
            original_filename="test.png",
            file_path=str(img_path),
            mime_type="image/png",
            page_count=1,
            status=DocumentStatus.REVIEWING,
            pages=[
                PageData(
                    page_number=1,
                    width=200,
                    height=200,
                    bitmap_path=str(img_path),
                    full_text="John Doe",
                ),
            ],
            regions=[
                PIIRegion(
                    page_number=1,
                    bbox=BBox(x0=10, y0=10, x1=100, y1=30),
                    text="John Doe",
                    pii_type=PIIType.PERSON,
                    confidence=0.99,
                    source=DetectionSource.REGEX,
                    char_start=0,
                    char_end=8,
                    action=RegionAction.REMOVE,
                ),
            ],
        )

        with patch("core.anonymizer.engine.vault", vault), \
             patch("core.anonymizer.engine.config") as mock_config:
            mock_config.temp_dir = tmp_path
            result = await anonymize_document(doc)

        assert isinstance(result, AnonymizeResponse)
        assert result.regions_removed == 1
        assert result.tokens_created == 0
        assert Path(result.output_path).exists()

    @pytest.mark.asyncio
    async def test_image_tokenize_region(self, vault: TokenVault, tmp_path: Path):
        """Tokenize region on an image — token stored in vault."""
        from PIL import Image

        img = Image.new("RGB", (300, 300), (255, 255, 255))
        img_path = tmp_path / "test.jpg"
        img.save(str(img_path), "JPEG")

        doc = DocumentInfo(
            original_filename="test.jpg",
            file_path=str(img_path),
            mime_type="image/jpeg",
            page_count=1,
            status=DocumentStatus.REVIEWING,
            pages=[
                PageData(
                    page_number=1,
                    width=300,
                    height=300,
                    bitmap_path=str(img_path),
                    full_text="acme@corp.com",
                ),
            ],
            regions=[
                PIIRegion(
                    page_number=1,
                    bbox=BBox(x0=10, y0=10, x1=150, y1=30),
                    text="acme@corp.com",
                    pii_type=PIIType.EMAIL,
                    confidence=0.95,
                    source=DetectionSource.REGEX,
                    char_start=0,
                    char_end=13,
                    action=RegionAction.TOKENIZE,
                ),
            ],
        )

        with patch("core.anonymizer.engine.vault", vault), \
             patch("core.anonymizer.engine.config") as mock_config:
            mock_config.temp_dir = tmp_path
            result = await anonymize_document(doc)

        assert result.tokens_created == 1
        assert result.regions_removed == 0
        assert Path(result.output_path).exists()

        # Manifest should contain the token (encrypted since vault is active)
        enc_path = tmp_path / doc.doc_id / "output" / "token_manifest.enc"
        assert enc_path.exists(), "Encrypted manifest not found"
        decrypted = vault.decrypt_blob(enc_path.read_bytes())
        manifest = json.loads(decrypted)
        assert len(manifest["tokens"]) == 1
        assert manifest["tokens"][0]["original_text"] == "acme@corp.com"

    @pytest.mark.asyncio
    async def test_image_no_regions(self, vault: TokenVault, tmp_path: Path):
        """Image with no active regions still produces an output file."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), (200, 200, 200))
        img_path = tmp_path / "grey.png"
        img.save(str(img_path), "PNG")

        doc = DocumentInfo(
            original_filename="grey.png",
            file_path=str(img_path),
            mime_type="image/png",
            page_count=1,
            status=DocumentStatus.REVIEWING,
            pages=[
                PageData(
                    page_number=1,
                    width=100,
                    height=100,
                    bitmap_path=str(img_path),
                    full_text="",
                ),
            ],
            regions=[],
        )

        with patch("core.anonymizer.engine.vault", vault), \
             patch("core.anonymizer.engine.config") as mock_config:
            mock_config.temp_dir = tmp_path
            result = await anonymize_document(doc)

        assert result.tokens_created == 0
        assert result.regions_removed == 0
        assert Path(result.output_path).exists()

    @pytest.mark.asyncio
    async def test_image_metadata_stripped(self, vault: TokenVault, tmp_path: Path):
        """Output image should have no EXIF metadata."""
        from PIL import Image

        img = Image.new("RGB", (50, 50), (128, 128, 128))
        img_path = tmp_path / "meta.jpg"
        img.save(str(img_path), "JPEG")

        doc = DocumentInfo(
            original_filename="meta.jpg",
            file_path=str(img_path),
            mime_type="image/jpeg",
            page_count=1,
            status=DocumentStatus.REVIEWING,
            pages=[
                PageData(
                    page_number=1,
                    width=50,
                    height=50,
                    bitmap_path=str(img_path),
                    full_text="",
                ),
            ],
            regions=[],
        )

        with patch("core.anonymizer.engine.vault", vault), \
             patch("core.anonymizer.engine.config") as mock_config:
            mock_config.temp_dir = tmp_path
            result = await anonymize_document(doc)

        out_img = Image.open(result.output_path)
        exif = out_img.getexif()
        assert len(exif) == 0, "Output image should have no EXIF data"


# ── PDF style extraction helpers ──────────────────────────────────────


class TestPDFStyleHelpers:
    def test_map_to_base14_sans_serif(self):
        from core.anonymizer.engine import _map_to_base14
        assert _map_to_base14("Arial", 0) == "helv"
        assert _map_to_base14("Arial", 16) == "hebo"      # bold
        assert _map_to_base14("Arial", 2) == "heit"        # italic
        assert _map_to_base14("Arial", 18) == "hebi"       # bold+italic

    def test_map_to_base14_serif(self):
        from core.anonymizer.engine import _map_to_base14
        assert _map_to_base14("TimesNewRoman", 4) == "tiro"
        assert _map_to_base14("Garamond", 20) == "tibo"    # bold+serif

    def test_map_to_base14_monospace(self):
        from core.anonymizer.engine import _map_to_base14
        assert _map_to_base14("Courier", 8) == "cour"
        assert _map_to_base14("ConsoleFont", 8) == "cour"

    def test_srgb_int_to_rgb(self):
        from core.anonymizer.engine import _srgb_int_to_rgb
        assert _srgb_int_to_rgb(0x000000) == (0.0, 0.0, 0.0)
        assert _srgb_int_to_rgb(0xFFFFFF) == (1.0, 1.0, 1.0)
        r, g, b = _srgb_int_to_rgb(0xFF0000)
        assert abs(r - 1.0) < 0.01 and abs(g) < 0.01 and abs(b) < 0.01
