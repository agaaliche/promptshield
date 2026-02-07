"""Document ingestion — load files of various formats and convert to page bitmaps + text."""

from __future__ import annotations

import logging
import mimetypes
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
from PIL import Image

from core.config import config
from core.ocr.engine import ocr_page_image
from models.schemas import BBox, DocumentInfo, DocumentStatus, PageData, TextBlock

logger = logging.getLogger(__name__)

# Supported MIME types
PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp"}
OFFICE_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",   # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",          # xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
}

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp",
    ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
}


def guess_mime(filepath: Path) -> str:
    """Guess MIME type from file extension."""
    mime, _ = mimetypes.guess_type(str(filepath))
    return mime or "application/octet-stream"


def _libreoffice_convert_to_pdf(src: Path, out_dir: Path) -> Path:
    """Convert an Office document to PDF using LibreOffice headless."""
    lo_cmd = shutil.which("libreoffice") or shutil.which("soffice")
    if lo_cmd is None:
        raise RuntimeError(
            "LibreOffice is required to process Office documents but was not found on PATH. "
            "Install LibreOffice and ensure 'libreoffice' or 'soffice' is available."
        )
    subprocess.run(
        [lo_cmd, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(src)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    pdf_path = out_dir / f"{src.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice conversion failed — expected output at {pdf_path}")
    return pdf_path


def _extract_text_blocks_from_page(pdf_page: pdfium.PdfPage, page_index: int) -> list[TextBlock]:
    """Extract word-level text blocks with bounding boxes from a PDF page."""
    textpage = pdf_page.get_textpage()
    full_text = textpage.get_text_range()

    blocks: list[TextBlock] = []
    if not full_text.strip():
        return blocks

    # Use character-level extraction and group into words
    n_chars = textpage.count_chars()
    if n_chars == 0:
        return blocks

    current_word = ""
    word_x0 = word_y0 = word_x1 = word_y1 = 0.0
    word_start_idx = 0
    word_index = 0

    for i in range(n_chars):
        char = textpage.get_text_range(index=i, count=1)
        charbox = textpage.get_charbox(i)  # (left, bottom, right, top) in PDF coords

        if char.strip() == "":
            # End of word — flush if we have accumulated text
            if current_word:
                # pypdfium2 charbox is (left, bottom, right, top) in PDF coords
                # Convert to top-left origin: y0 = page_height - top, y1 = page_height - bottom
                page_height = pdf_page.get_height()
                blocks.append(TextBlock(
                    text=current_word,
                    bbox=BBox(
                        x0=word_x0,
                        y0=page_height - word_y1,  # top in screen coords
                        x1=word_x1,
                        y1=page_height - word_y0,  # bottom in screen coords
                    ),
                    confidence=1.0,
                    block_index=0,
                    line_index=0,
                    word_index=word_index,
                    is_ocr=False,
                ))
                word_index += 1
                current_word = ""
        else:
            left, bottom, right, top = charbox
            if not current_word:
                word_x0 = left
                word_y0 = bottom
                word_x1 = right
                word_y1 = top
                word_start_idx = i
            else:
                word_x0 = min(word_x0, left)
                word_y0 = min(word_y0, bottom)
                word_x1 = max(word_x1, right)
                word_y1 = max(word_y1, top)
            current_word += char

    # Flush last word
    if current_word:
        page_height = pdf_page.get_height()
        blocks.append(TextBlock(
            text=current_word,
            bbox=BBox(
                x0=word_x0,
                y0=page_height - word_y1,
                x1=word_x1,
                y1=page_height - word_y0,
            ),
            confidence=1.0,
            block_index=0,
            line_index=0,
            word_index=word_index,
            is_ocr=False,
        ))

    return blocks


def _render_page_bitmap(pdf_page: pdfium.PdfPage, page_index: int, doc_id: str) -> Path:
    """Render a PDF page to a PNG bitmap."""
    scale = config.render_dpi / 72  # PDF default is 72 DPI
    bitmap = pdf_page.render(scale=scale)
    pil_image = bitmap.to_pil()

    out_path = config.temp_dir / doc_id / f"page_{page_index + 1:04d}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil_image.save(str(out_path), "PNG")
    return out_path


def _process_pdf(pdf_path: Path, doc_id: str) -> list[PageData]:
    """Process a PDF file into page data."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    pages: list[PageData] = []

    for i in range(len(pdf)):
        pdf_page = pdf[i]
        width = pdf_page.get_width()
        height = pdf_page.get_height()

        # Render bitmap
        bitmap_path = _render_page_bitmap(pdf_page, i, doc_id)

        # Extract text with bounding boxes
        text_blocks = _extract_text_blocks_from_page(pdf_page, i)

        # If very few text blocks found, page might be scanned — try OCR
        full_text = " ".join(b.text for b in text_blocks)
        if len(full_text.strip()) < 20:
            logger.info(f"Page {i + 1}: sparse text ({len(full_text)} chars), running OCR")
            ocr_blocks = ocr_page_image(bitmap_path, width, height)
            if ocr_blocks:
                text_blocks = ocr_blocks
                full_text = " ".join(b.text for b in text_blocks)

        pages.append(PageData(
            page_number=i + 1,
            width=width,
            height=height,
            bitmap_path=str(bitmap_path),
            text_blocks=text_blocks,
            full_text=full_text,
        ))

    return pages


def _process_image(image_path: Path, doc_id: str) -> list[PageData]:
    """Process a standalone image file (always OCR)."""
    img = Image.open(image_path)
    width, height = img.size

    # Save as PNG in temp
    out_path = config.temp_dir / doc_id / "page_0001.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG")

    # OCR is required for images
    text_blocks = ocr_page_image(out_path, float(width), float(height))
    full_text = " ".join(b.text for b in text_blocks)

    return [PageData(
        page_number=1,
        width=float(width),
        height=float(height),
        bitmap_path=str(out_path),
        text_blocks=text_blocks,
        full_text=full_text,
    )]


async def ingest_document(
    file_path: Path,
    original_filename: str,
    mime_type: Optional[str] = None,
) -> DocumentInfo:
    """
    Main entry point: ingest a document file, convert to bitmaps, extract text.

    Returns a DocumentInfo with pages populated.
    """
    doc_id = uuid.uuid4().hex[:12]
    if mime_type is None:
        mime_type = guess_mime(file_path)

    logger.info(f"Ingesting '{original_filename}' (mime={mime_type}, id={doc_id})")

    doc = DocumentInfo(
        doc_id=doc_id,
        original_filename=original_filename,
        file_path=str(file_path),
        mime_type=mime_type,
        status=DocumentStatus.PROCESSING,
    )

    try:
        if mime_type in PDF_TYPES:
            doc.pages = _process_pdf(file_path, doc_id)
        elif mime_type in IMAGE_TYPES:
            doc.pages = _process_image(file_path, doc_id)
        elif mime_type in OFFICE_TYPES:
            # Convert to PDF first
            pdf_path = _libreoffice_convert_to_pdf(
                file_path,
                config.temp_dir / doc_id,
            )
            doc.pages = _process_pdf(pdf_path, doc_id)
        else:
            raise ValueError(f"Unsupported file type: {mime_type}")

        doc.page_count = len(doc.pages)
        doc.status = DocumentStatus.DETECTING
        logger.info(f"Ingested {doc.page_count} pages from '{original_filename}'")

    except Exception as e:
        logger.exception(f"Failed to ingest '{original_filename}'")
        doc.status = DocumentStatus.ERROR
        raise

    return doc
