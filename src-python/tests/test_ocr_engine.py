"""Tests for the OCR engine — unit-level (no Tesseract required)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from core.ocr.engine import _check_tesseract, ocr_page_image


class TestCheckTesseract:
    def test_returns_bool(self):
        """_check_tesseract should return True or False."""
        import core.ocr.engine as mod
        # Reset the cached flag to force re-evaluation
        old_val = mod._tesseract_available
        mod._tesseract_available = None
        result = _check_tesseract()
        assert isinstance(result, bool)
        mod._tesseract_available = old_val  # restore

    def test_caches_result(self):
        """Once checked, the result is cached (no re-import)."""
        import core.ocr.engine as mod
        mod._tesseract_available = True
        assert _check_tesseract() is True
        mod._tesseract_available = False
        assert _check_tesseract() is False
        mod._tesseract_available = None  # reset for other tests


class TestOCRPageImage:
    def test_returns_empty_when_tesseract_unavailable(self):
        """If Tesseract is unavailable, return empty list."""
        import core.ocr.engine as mod
        old_val = mod._tesseract_available
        mod._tesseract_available = False

        result = ocr_page_image(Path("fake.png"), 612.0, 792.0)
        assert result == []

        mod._tesseract_available = old_val

    def test_returns_textblocks_with_mock_tesseract(self):
        """Simulate Tesseract output and verify TextBlock generation."""
        import core.ocr.engine as mod
        old_val = mod._tesseract_available
        mod._tesseract_available = True

        mock_data = {
            "text": ["Hello", "World", ""],
            "left": [10, 100, 0],
            "top": [20, 20, 0],
            "width": [40, 50, 0],
            "height": [12, 12, 0],
            "conf": [90, 85, -1],
            "block_num": [1, 1, 0],
            "line_num": [1, 1, 0],
            "word_num": [1, 2, 0],
        }

        mock_image = MagicMock()
        mock_image.size = (300, 400)
        mock_image.close = MagicMock()

        import sys
        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = mock_data
        sys.modules["pytesseract"] = mock_pytesseract

        with patch("PIL.Image.open", return_value=mock_image):
            result = ocr_page_image(Path("test.png"), 600.0, 800.0)

        del sys.modules["pytesseract"]

        # Should have 2 non-empty text blocks
        assert len(result) == 2
        assert result[0].text == "Hello"
        assert result[1].text == "World"

        mod._tesseract_available = old_val
