"""OCR engine — Tesseract integration for scanned documents and images."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from models.schemas import BBox, TextBlock

logger = logging.getLogger(__name__)

_tesseract_available: bool | None = None


def _check_tesseract() -> bool:
    """Check if Tesseract is available on the system."""
    global _tesseract_available
    if _tesseract_available is not None:
        return _tesseract_available

    try:
        import pytesseract
        from core.config import config

        if config.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
        elif shutil.which("tesseract") is None:
            # Try common Windows install path
            common_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for p in common_paths:
                if Path(p).exists():
                    pytesseract.pytesseract.tesseract_cmd = p
                    break

        # Test it works
        pytesseract.get_tesseract_version()
        _tesseract_available = True
        logger.info("Tesseract OCR is available")
    except Exception as e:
        logger.warning(f"Tesseract OCR not available: {e}")
        _tesseract_available = False

    return _tesseract_available


def ocr_page_image(
    image_path: Path,
    page_width: float,
    page_height: float,
) -> list[TextBlock]:
    """
    Run OCR on a page bitmap image.

    Returns word-level TextBlock instances with bounding boxes scaled
    to match the original page coordinate space.
    """
    if not _check_tesseract():
        logger.warning("Tesseract not available — skipping OCR")
        return []

    import pytesseract
    from PIL import Image
    from core.config import config

    img = Image.open(image_path)
    img_width, img_height = img.size

    # Scale factors to convert pixel coords → page coords
    sx = page_width / img_width
    sy = page_height / img_height

    data = pytesseract.image_to_data(
        img,
        lang=config.ocr_language,
        output_type=pytesseract.Output.DICT,
        config=f"--oem 1 --psm 6 --dpi {config.ocr_dpi}",
    )

    blocks: list[TextBlock] = []
    n_items = len(data["text"])

    for i in range(n_items):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])

        # Skip empty / low-confidence entries
        # Raise threshold from 0 to 30 to reduce garbage tokens
        if not text or conf < 30:
            continue

        # Tesseract returns pixel-based bounding boxes
        px_left = data["left"][i]
        px_top = data["top"][i]
        px_width = data["width"][i]
        px_height = data["height"][i]

        blocks.append(TextBlock(
            text=text,
            bbox=BBox(
                x0=px_left * sx,
                y0=px_top * sy,
                x1=(px_left + px_width) * sx,
                y1=(px_top + px_height) * sy,
            ),
            confidence=conf / 100.0,
            block_index=data["block_num"][i],
            line_index=data["line_num"][i],
            word_index=data["word_num"][i],
            is_ocr=True,
        ))

    logger.info(f"OCR extracted {len(blocks)} words from {image_path.name}")
    return blocks
