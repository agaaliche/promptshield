"""Anonymization engine — applies redaction and tokenization to documents."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image, ImageDraw

from core.config import config
from core.vault.store import vault
from models.schemas import (
    AnonymizeResponse,
    DocumentInfo,
    PIIRegion,
    PIIType,
    RegionAction,
    TokenMapping,
)

logger = logging.getLogger(__name__)

# File type constants
PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp"}
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def anonymize_document(doc: DocumentInfo) -> AnonymizeResponse:
    """
    Apply all accepted region actions to a document and produce output files.

    Dispatches to the appropriate handler based on file type:
    - PDF: Text-based redaction with PyMuPDF
    - DOCX: Text replacement in paragraphs/tables
    - XLSX: Text replacement in cells
    - Images: Bitmap manipulation
    """
    if not vault.is_unlocked:
        raise RuntimeError("Vault must be unlocked before anonymization")

    original_path = Path(doc.file_path)
    if not original_path.exists():
        raise RuntimeError(f"Original file not found: {original_path}")

    # Dispatch to appropriate handler based on MIME type
    if doc.mime_type in PDF_TYPES:
        return await _anonymize_pdf(doc, original_path)
    elif doc.mime_type == DOCX_TYPE:
        return await _anonymize_docx(doc, original_path)
    elif doc.mime_type == XLSX_TYPE:
        return await _anonymize_xlsx(doc, original_path)
    elif doc.mime_type in IMAGE_TYPES:
        return await _anonymize_image(doc, original_path)
    else:
        raise ValueError(f"Unsupported file type for anonymization: {doc.mime_type}")


async def _anonymize_pdf(doc: DocumentInfo, original_path: Path) -> AnonymizeResponse:
    """Anonymize a PDF file using text-based redactions."""
    tokens_created = 0
    regions_removed = 0
    token_manifest: list[dict] = []

    # Open PDF with PyMuPDF
    pdf_doc = fitz.open(str(original_path))

    try:
        # Process regions grouped by page
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            page_regions = [
                r for r in doc.regions if r.page_number == page_num + 1
            ]

            for region in page_regions:
                if region.action == RegionAction.REMOVE:
                    # Replace with hyphens
                    replacement_text = "---"
                    _add_text_redaction(page, region, doc.pages[page_num], replacement_text)
                    regions_removed += 1

                elif region.action == RegionAction.TOKENIZE:
                    # Generate token
                    token_string = vault.generate_token_string(region.pii_type)

                    # Store in vault
                    mapping = TokenMapping(
                        token_string=token_string,
                        original_text=region.text,
                        pii_type=region.pii_type,
                        source_document=doc.original_filename,
                        context_snippet=_get_context_snippet(
                            doc.pages[page_num].full_text,
                            region.char_start,
                            region.char_end,
                        ),
                    )
                    vault.store_token(mapping)

                    # Add as redaction with token text
                    _add_text_redaction(page, region, doc.pages[page_num], token_string)
                    tokens_created += 1

                    # Record for detokenization manifest
                    token_manifest.append({
                        "token_string": token_string,
                        "original_text": region.text,
                        "page_number": page_num + 1,
                    })

            # Apply all redactions on this page
            page.apply_redactions()

        # Save anonymized PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = Path(doc.original_filename).stem
        output_dir = config.temp_dir / doc.doc_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = output_dir / f"{stem}_anonymized_{timestamp}.pdf"
        pdf_doc.save(str(pdf_path), deflate=True, clean=True)
        logger.info(f"Saved anonymized PDF: {pdf_path}")

        # Save token manifest for detokenization
        manifest_path = output_dir / "token_manifest.json"
        manifest_path.write_text(
            json.dumps({
                "doc_id": doc.doc_id,
                "original_filename": doc.original_filename,
                "tokens": token_manifest,
            }, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Saved token manifest with {len(token_manifest)} token entries")

        # Register in vault
        vault.register_document(
            doc_id=doc.doc_id,
            original_filename=doc.original_filename,
            page_count=doc.page_count,
            anonymized_filename=pdf_path.name,
        )

        logger.info(
            f"Anonymized '{doc.original_filename}': "
            f"{regions_removed} removed, {tokens_created} tokenized"
        )

        return AnonymizeResponse(
            doc_id=doc.doc_id,
            output_path=str(pdf_path),
            output_text_path="",
            tokens_created=tokens_created,
            regions_removed=regions_removed,
        )

    finally:
        pdf_doc.close()


def _replace_in_paragraphs(paragraphs, replacements: dict[str, str]) -> None:
    """Replace text in DOCX paragraphs, handling cross-run PII spans.

    For each paragraph:
    1. Join all run texts into a single string.
    2. Apply all replacements on the joined text.
    3. If the text changed, rewrite the paragraph into a single run
       (preserving the formatting of the first run).

    This handles PII that is split across multiple XML runs
    (e.g., "Joh" | "n S" | "mith") — per-run replacement would miss those.
    """
    for paragraph in paragraphs:
        runs = paragraph.runs
        if not runs:
            continue
        full = "".join(r.text for r in runs)
        if not full:
            continue
        replaced = full
        for original, replacement in replacements.items():
            replaced = replaced.replace(original, replacement)
        if replaced == full:
            continue
        # Rewrite: keep first run (preserves font/style), clear the rest
        fmt = runs[0].font  # noqa: F841 — we keep the run object alive
        runs[0].text = replaced
        for r in runs[1:]:
            r.text = ""


async def _anonymize_docx(doc: DocumentInfo, original_path: Path) -> AnonymizeResponse:
    """Anonymize a DOCX file using text replacements."""
    from docx import Document
    
    tokens_created = 0
    regions_removed = 0
    token_manifest: list[dict] = []

    # Open DOCX
    docx = Document(str(original_path))

    # Sort regions by char_end descending to preserve offsets during replacement
    sorted_regions = sorted(
        [r for r in doc.regions if r.action in (RegionAction.REMOVE, RegionAction.TOKENIZE)],
        key=lambda r: r.char_end,
        reverse=True,
    )

    # Build full text to find replacements
    full_text = doc.pages[0].full_text if doc.pages else ""

    # Track replacements
    replacements: dict[str, str] = {}

    for region in sorted_regions:
        original_text = region.text

        if region.action == RegionAction.REMOVE:
            replacement = "---"
            replacements[original_text] = replacement
            regions_removed += 1

        elif region.action == RegionAction.TOKENIZE:
            token_string = vault.generate_token_string(region.pii_type)

            mapping = TokenMapping(
                token_string=token_string,
                original_text=original_text,
                pii_type=region.pii_type,
                source_document=doc.original_filename,
                context_snippet=_get_context_snippet(full_text, region.char_start, region.char_end),
            )
            vault.store_token(mapping)

            replacements[original_text] = token_string
            tokens_created += 1

            token_manifest.append({
                "token_string": token_string,
                "original_text": original_text,
            })

    # Apply replacements to all text in document
    # DOCX paragraphs may split a PII span across multiple runs.
    # Per-run string replace fails in that case.  Instead, do
    # paragraph-level replacement: join all runs, replace, then
    # rewrite into a single run (preserving the first run's format).
    _replace_in_paragraphs(docx.paragraphs, replacements)

    # Apply to tables
    for table in docx.tables:
        for row in table.rows:
            for cell in row.cells:
                _replace_in_paragraphs(cell.paragraphs, replacements)

    # Save anonymized DOCX
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(doc.original_filename).stem
    output_dir = config.temp_dir / doc.doc_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    docx_path = output_dir / f"{stem}_anonymized_{timestamp}.docx"
    docx.save(str(docx_path))
    logger.info(f"Saved anonymized DOCX: {docx_path}")

    # Save token manifest
    manifest_path = output_dir / "token_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "doc_id": doc.doc_id,
            "original_filename": doc.original_filename,
            "tokens": token_manifest,
        }, indent=2),
        encoding="utf-8",
    )

    vault.register_document(
        doc_id=doc.doc_id,
        original_filename=doc.original_filename,
        page_count=doc.page_count,
        anonymized_filename=docx_path.name,
    )

    logger.info(
        f"Anonymized DOCX '{doc.original_filename}': "
        f"{regions_removed} removed, {tokens_created} tokenized"
    )

    return AnonymizeResponse(
        doc_id=doc.doc_id,
        output_path=str(docx_path),
        output_text_path="",
        tokens_created=tokens_created,
        regions_removed=regions_removed,
    )


async def _anonymize_xlsx(doc: DocumentInfo, original_path: Path) -> AnonymizeResponse:
    """Anonymize an XLSX file using text replacements in cells."""
    from openpyxl import load_workbook

    tokens_created = 0
    regions_removed = 0
    token_manifest: list[dict] = []

    # Open XLSX
    wb = load_workbook(str(original_path))

    # Build full text to match regions
    full_text = doc.pages[0].full_text if doc.pages else ""

    # Sort regions by char_end descending
    sorted_regions = sorted(
        [r for r in doc.regions if r.action in (RegionAction.REMOVE, RegionAction.TOKENIZE)],
        key=lambda r: r.char_end,
        reverse=True,
    )

    # Track replacements
    replacements: dict[str, str] = {}

    for region in sorted_regions:
        original_text = region.text

        if region.action == RegionAction.REMOVE:
            replacement = "---"
            replacements[original_text] = replacement
            regions_removed += 1

        elif region.action == RegionAction.TOKENIZE:
            token_string = vault.generate_token_string(region.pii_type)

            mapping = TokenMapping(
                token_string=token_string,
                original_text=original_text,
                pii_type=region.pii_type,
                source_document=doc.original_filename,
                context_snippet=_get_context_snippet(full_text, region.char_start, region.char_end),
            )
            vault.store_token(mapping)

            replacements[original_text] = token_string
            tokens_created += 1

            token_manifest.append({
                "token_string": token_string,
                "original_text": original_text,
            })

    # Apply replacements to all cells
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value:
                    for original, replacement in replacements.items():
                        cell.value = cell.value.replace(original, replacement)

    # Save anonymized XLSX
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(doc.original_filename).stem
    output_dir = config.temp_dir / doc.doc_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    xlsx_path = output_dir / f"{stem}_anonymized_{timestamp}.xlsx"
    wb.save(str(xlsx_path))
    logger.info(f"Saved anonymized XLSX: {xlsx_path}")

    # Save token manifest
    manifest_path = output_dir / "token_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "doc_id": doc.doc_id,
            "original_filename": doc.original_filename,
            "tokens": token_manifest,
        }, indent=2),
        encoding="utf-8",
    )

    vault.register_document(
        doc_id=doc.doc_id,
        original_filename=doc.original_filename,
        page_count=doc.page_count,
        anonymized_filename=xlsx_path.name,
    )

    logger.info(
        f"Anonymized XLSX '{doc.original_filename}': "
        f"{regions_removed} removed, {tokens_created} tokenized"
    )

    return AnonymizeResponse(
        doc_id=doc.doc_id,
        output_path=str(xlsx_path),
        output_text_path="",
        tokens_created=tokens_created,
        regions_removed=regions_removed,
    )


async def _anonymize_image(doc: DocumentInfo, original_path: Path) -> AnonymizeResponse:
    """Anonymize an image file using bitmap manipulation."""
    tokens_created = 0
    regions_removed = 0
    token_manifest: list[dict] = []

    # Load the original image
    img = Image.open(str(original_path)).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Get page dimensions
    page_data = doc.pages[0] if doc.pages else None
    if not page_data:
        raise ValueError("No page data available for image")

    full_text = page_data.full_text

    # Process all annotated regions
    for region in doc.regions:
        if region.action == RegionAction.REMOVE:
            # Draw white rectangle (clean removal)
            bbox = region.bbox
            draw.rectangle(
                [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                fill=(255, 255, 255),
            )
            regions_removed += 1

        elif region.action == RegionAction.TOKENIZE:
            token_string = vault.generate_token_string(region.pii_type)

            mapping = TokenMapping(
                token_string=token_string,
                original_text=region.text,
                pii_type=region.pii_type,
                source_document=doc.original_filename,
                context_snippet=_get_context_snippet(full_text, region.char_start, region.char_end),
            )
            vault.store_token(mapping)

            # Draw white rectangle then add token text
            bbox = region.bbox
            draw.rectangle(
                [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                fill=(255, 255, 255),
            )
            # Draw token text in black
            draw.text(
                (bbox.x0 + 2, bbox.y0 + 2),
                token_string,
                fill=(0, 0, 0),
            )
            tokens_created += 1

            token_manifest.append({
                "token_string": token_string,
                "original_text": region.text,
            })

    # Save anonymized image with original extension
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(doc.original_filename).stem
    ext = Path(doc.original_filename).suffix.lower()
    output_dir = config.temp_dir / doc.doc_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    img_path = output_dir / f"{stem}_anonymized_{timestamp}{ext}"
    
    # Save with appropriate format
    if ext in [".jpg", ".jpeg"]:
        img.save(str(img_path), "JPEG", quality=95)
    elif ext == ".png":
        img.save(str(img_path), "PNG")
    else:
        img.save(str(img_path))
    
    logger.info(f"Saved anonymized image: {img_path}")

    # Save token manifest
    manifest_path = output_dir / "token_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "doc_id": doc.doc_id,
            "original_filename": doc.original_filename,
            "tokens": token_manifest,
        }, indent=2),
        encoding="utf-8",
    )

    vault.register_document(
        doc_id=doc.doc_id,
        original_filename=doc.original_filename,
        page_count=doc.page_count,
        anonymized_filename=img_path.name,
    )

    logger.info(
        f"Anonymized image '{doc.original_filename}': "
        f"{regions_removed} removed, {tokens_created} tokenized"
    )

    return AnonymizeResponse(
        doc_id=doc.doc_id,
        output_path=str(img_path),
        output_text_path="",
        tokens_created=tokens_created,
        regions_removed=regions_removed,
    )


def _add_text_redaction(
    page: fitz.Page,
    region: PIIRegion,
    page_data,
    replacement_text: str,
) -> None:
    """Add a redaction annotation with replacement text."""
    # Convert page coordinates to PyMuPDF rect
    # page_data has width/height in PDF points
    bbox = region.bbox
    rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    
    # Add redaction annotation with replacement text
    # fill: color for the redacted area (white to keep PDF clean)
    # text: replacement text to insert
    page.add_redact_annot(
        rect,
        text=replacement_text,
        fill=(1, 1, 1),  # White fill (no visual styling)
        text_color=(0, 0, 0),  # Black text
        fontsize=10,
    )


def _get_context_snippet(text: str, start: int, end: int, context_chars: int = 50) -> str:
    """Extract a text snippet around the PII for disambiguation."""
    ctx_start = max(0, start - context_chars)
    ctx_end = min(len(text), end + context_chars)
    snippet = text[ctx_start:ctx_end]
    if ctx_start > 0:
        snippet = "..." + snippet
    if ctx_end < len(text):
        snippet = snippet + "..."
    return snippet
