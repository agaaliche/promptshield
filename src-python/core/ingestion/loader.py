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


def _cluster_into_lines(text_blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Group text blocks into visual lines by y-proximity, then sort
    left-to-right within each line.

    Plain ``sorted(blocks, key=(y0, x0))`` can mis-order words on the
    same visual line when their y0 values differ slightly (common with
    ascenders/descenders in PDF extraction and OCR noise).  Clustering
    by y-center avoids this.
    """
    if not text_blocks:
        return []

    by_y = sorted(text_blocks, key=lambda b: (b.bbox.y0 + b.bbox.y1) / 2)

    lines: list[list[TextBlock]] = []
    cur_line: list[TextBlock] = []
    line_yc: float = 0.0
    line_h: float = 0.0

    for block in by_y:
        bh = block.bbox.y1 - block.bbox.y0
        byc = (block.bbox.y0 + block.bbox.y1) / 2

        if not cur_line:
            cur_line.append(block)
            line_yc = byc
            line_h = bh
        else:
            tolerance = max(line_h, bh) * 0.5
            if abs(byc - line_yc) <= tolerance:
                cur_line.append(block)
                line_h = max(line_h, bh)
                n = len(cur_line)
                line_yc = (line_yc * (n - 1) + byc) / n
            else:
                lines.append(sorted(cur_line, key=lambda b: b.bbox.x0))
                cur_line = [block]
                line_yc = byc
                line_h = bh

    if cur_line:
        lines.append(sorted(cur_line, key=lambda b: b.bbox.x0))

    return lines


def _build_full_text(text_blocks: list[TextBlock]) -> str:
    """Build full_text from text blocks, inserting newlines between
    lines that are spatially separated (different vertical position).

    Blocks are clustered into visual lines (tolerant of minor y-position
    differences from ascenders, descenders, or OCR noise) and sorted
    left-to-right within each line, producing correct reading order.

    This gives NER/regex much better input than a flat space-joined
    string because sentence boundaries are preserved.
    """
    if not text_blocks:
        return ""

    lines = _cluster_into_lines(text_blocks)

    parts: list[str] = []
    prev_y: float | None = None
    line_height = 0.0

    for line_blocks in lines:
        line_top = min(b.bbox.y0 for b in line_blocks)
        lh = max(b.bbox.y1 for b in line_blocks) - line_top

        for i, block in enumerate(line_blocks):
            if prev_y is not None or i > 0:
                if i == 0:
                    gap = line_top - prev_y if prev_y is not None else 0
                    if line_height > 0 and gap > line_height * 0.6:
                        parts.append("\n")
                    else:
                        parts.append(" ")
                else:
                    parts.append(" ")
            parts.append(block.text)

        prev_y = line_top
        line_height = lh

    return "".join(parts).strip()


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


def _is_rotated_word(char_y_centers: list[float], char_heights: list[float]) -> bool:
    """Return True if the accumulated character positions indicate rotated text.

    For horizontal text, all characters share roughly the same y-centre.
    For rotated/diagonal text (watermarks), the y-centres of successive
    characters shift significantly — the vertical spread of centres will
    exceed a fraction of the average character height.

    Punctuation marks (periods, commas, apostrophes) and accent marks have
    much smaller bounding boxes positioned at different baselines than the
    main letter glyphs.  Without filtering them out, a word like ``B.N.``
    or ``l'exercice`` would look "rotated" even though it's perfectly
    horizontal.  We therefore exclude characters whose height is less than
    70 % of the median character height before computing the spread.
    """
    if len(char_y_centers) < 2:
        return False

    # --- filter out small characters (punctuation / accents / superscripts) ---
    sorted_h = sorted(char_heights)
    n = len(sorted_h)
    median_h = sorted_h[n // 2] if n % 2 == 1 else (sorted_h[n // 2 - 1] + sorted_h[n // 2]) / 2.0
    height_threshold = median_h * 0.70

    filtered_yc: list[float] = []
    filtered_h: list[float] = []
    for yc, h in zip(char_y_centers, char_heights):
        if h >= height_threshold:
            filtered_yc.append(yc)
            filtered_h.append(h)

    if len(filtered_yc) < 2:
        return False

    y_spread = max(filtered_yc) - min(filtered_yc)
    avg_h = sum(filtered_h) / len(filtered_h)
    # Horizontal text: y_spread ≈ 0.  45° rotated: y_spread ≈ word width.
    # Threshold raised to 0.65 to tolerate accented capitals (É, Ô, …) whose
    # taller bounding-box shifts the y-centre slightly.
    return y_spread > avg_h * 0.65


def _extract_text_blocks_from_page(pdf_page: pdfium.PdfPage, page_index: int) -> list[TextBlock]:
    """Extract word-level text blocks with bounding boxes from a PDF page.

    Rotated text (diagonal watermarks, etc.) is automatically discarded.
    """
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
    # Per-character tracking for rotation detection
    char_y_centers: list[float] = []
    char_heights: list[float] = []
    rotated_skipped = 0

    for i in range(n_chars):
        char = textpage.get_text_range(index=i, count=1)
        charbox = textpage.get_charbox(i)  # (left, bottom, right, top) in PDF coords

        if char.strip() == "":
            # End of word — flush if we have accumulated text
            if current_word:
                if _is_rotated_word(char_y_centers, char_heights):
                    rotated_skipped += 1
                else:
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
                char_y_centers = []
                char_heights = []
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
            char_y_centers.append((bottom + top) / 2.0)
            char_heights.append(top - bottom)

    # Flush last word
    if current_word:
        if _is_rotated_word(char_y_centers, char_heights):
            rotated_skipped += 1
        else:
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

    if rotated_skipped:
        import logging
        logging.getLogger(__name__).info(
            f"Page {page_index + 1}: discarded {rotated_skipped} rotated "
            f"text block(s) (watermarks/diagonal text)"
        )

    return blocks


def _render_page_bitmap(pdf_page: pdfium.PdfPage, page_index: int, doc_id: str) -> Path:
    """Render a PDF page to a PNG bitmap."""
    scale = config.render_dpi / 72  # PDF default is 72 DPI
    bitmap = pdf_page.render(scale=scale)
    pil_image = bitmap.to_pil()

    out_path = config.temp_dir / doc_id / f"page_{page_index + 1:04d}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pil_image.save(str(out_path), "PNG")
    pil_image.close()
    del bitmap
    return out_path


def _process_pdf(pdf_path: Path, doc_id: str) -> list[PageData]:
    """Process a PDF file into page data."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
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
            full_text = _build_full_text(text_blocks)
            if len(full_text.strip()) < 20:
                logger.info(f"Page {i + 1}: sparse text ({len(full_text)} chars), running OCR")
                ocr_blocks = ocr_page_image(bitmap_path, width, height)
                if ocr_blocks:
                    text_blocks = ocr_blocks
                    full_text = _build_full_text(text_blocks)

            pages.append(PageData(
                page_number=i + 1,
                width=width,
                height=height,
                bitmap_path=str(bitmap_path),
                text_blocks=text_blocks,
                full_text=full_text,
            ))

        return pages
    finally:
        pdf.close()


def _process_image(image_path: Path, doc_id: str) -> list[PageData]:
    """Process a standalone image file (always OCR)."""
    img = Image.open(image_path)
    try:
        width, height = img.size

        # Save as PNG in temp
        out_path = config.temp_dir / doc_id / "page_0001.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Upscale small images to improve OCR accuracy
        min_dim = min(width, height)
        if min_dim < 1500:
            scale = max(2, 1500 // min_dim)
            big = img.resize((width * scale, height * scale), Image.LANCZOS)
            big.save(str(out_path), "PNG")
            big.close()
            logger.info(f"Upscaled image {width}x{height} by {scale}x for OCR")
        else:
            img.save(str(out_path), "PNG")

        # OCR is required for images
        text_blocks = ocr_page_image(out_path, float(width), float(height))
        full_text = _build_full_text(text_blocks)

        return [PageData(
            page_number=1,
            width=float(width),
            height=float(height),
            bitmap_path=str(out_path),
            text_blocks=text_blocks,
            full_text=full_text,
        )]
    finally:
        img.close()


async def ingest_document(
    file_path: Path,
    original_filename: str,
    mime_type: Optional[str] = None,
) -> DocumentInfo:
    """
    Main entry point: ingest a document file, convert to bitmaps, extract text.

    Returns a DocumentInfo with pages populated.
    """
    import asyncio

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

    def _do_ingest() -> list:
        if mime_type in PDF_TYPES:
            return _process_pdf(file_path, doc_id)
        elif mime_type in IMAGE_TYPES:
            return _process_image(file_path, doc_id)
        elif mime_type in OFFICE_TYPES:
            pdf_path = _libreoffice_convert_to_pdf(
                file_path,
                config.temp_dir / doc_id,
            )
            return _process_pdf(pdf_path, doc_id)
        else:
            raise ValueError(f"Unsupported file type: {mime_type}")

    try:
        doc.pages = await asyncio.to_thread(_do_ingest)

        doc.page_count = len(doc.pages)
        doc.status = DocumentStatus.DETECTING
        logger.info(f"Ingested {doc.page_count} pages from '{original_filename}'")

    except Exception as e:
        logger.exception(f"Failed to ingest '{original_filename}'")
        doc.status = DocumentStatus.ERROR
        raise

    return doc
