"""Anonymization engine — applies redaction and tokenization to documents."""

from __future__ import annotations

import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

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

# Redaction fill color
REDACT_COLOR = (0, 0, 0)         # Black rectangle
TOKENIZE_BG_COLOR = (50, 50, 180)  # Blue background for token text
TOKEN_TEXT_COLOR = (255, 255, 255)  # White text for tokens


def _get_font(size: int = 12):
    """Get a monospace font for drawing token text."""
    try:
        return ImageFont.truetype("cour.ttf", size)  # Courier on Windows
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSansMono.ttf", size)
        except OSError:
            return ImageFont.load_default()


def _apply_region_to_bitmap(
    image: Image.Image,
    region: PIIRegion,
    page_width: float,
    page_height: float,
    token_text: Optional[str] = None,
) -> None:
    """
    Apply a redaction or tokenization to a page bitmap in-place.

    Converts page coordinates to pixel coordinates and draws over the region.
    """
    img_width, img_height = image.size
    sx = img_width / page_width
    sy = img_height / page_height

    # Convert page coords to pixel coords
    px0 = int(region.bbox.x0 * sx)
    py0 = int(region.bbox.y0 * sy)
    px1 = int(region.bbox.x1 * sx)
    py1 = int(region.bbox.y1 * sy)

    # Clamp to image bounds
    px0 = max(0, min(px0, img_width - 1))
    py0 = max(0, min(py0, img_height - 1))
    px1 = max(0, min(px1, img_width - 1))
    py1 = max(0, min(py1, img_height - 1))

    draw = ImageDraw.Draw(image)

    if token_text:
        # Tokenize: blue background + white token text
        draw.rectangle([px0, py0, px1, py1], fill=TOKENIZE_BG_COLOR)

        # Fit font size to the rectangle
        rect_height = py1 - py0
        font_size = max(8, int(rect_height * 0.7))
        font = _get_font(font_size)

        # Center the token text
        text_bbox = draw.textbbox((0, 0), token_text, font=font)
        tw = text_bbox[2] - text_bbox[0]
        th = text_bbox[3] - text_bbox[1]
        tx = px0 + (px1 - px0 - tw) / 2
        ty = py0 + (py1 - py0 - th) / 2

        draw.text((tx, ty), token_text, fill=TOKEN_TEXT_COLOR, font=font)
    else:
        # Remove: black rectangle
        draw.rectangle([px0, py0, px1, py1], fill=REDACT_COLOR)


async def anonymize_document(doc: DocumentInfo) -> AnonymizeResponse:
    """
    Apply all accepted region actions to a document and produce output files.

    Regions with action REMOVE get black-box redaction.
    Regions with action TOKENIZE get token replacement.
    Regions with action CANCEL or PENDING are left unchanged.
    """
    if not vault.is_unlocked:
        raise RuntimeError("Vault must be unlocked before anonymization")

    tokens_created = 0
    regions_removed = 0
    anonymized_pages: list[Image.Image] = []
    text_lines: list[str] = []

    for page in doc.pages:
        # Load the page bitmap
        img = Image.open(page.bitmap_path).convert("RGB")

        # Build the page text, applying modifications
        page_text = page.full_text

        # Process regions for this page (sorted by position, reverse order for text replacement)
        page_regions = [
            r for r in doc.regions if r.page_number == page.page_number
        ]
        page_regions_for_text = sorted(
            page_regions, key=lambda r: r.char_start, reverse=True
        )

        for region in page_regions:
            if region.action == RegionAction.REMOVE:
                # Black-box redaction on bitmap
                _apply_region_to_bitmap(
                    img, region, page.width, page.height
                )
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
                        page.full_text, region.char_start, region.char_end
                    ),
                )
                vault.store_token(mapping)

                # Draw token on bitmap
                _apply_region_to_bitmap(
                    img, region, page.width, page.height,
                    token_text=token_string,
                )
                tokens_created += 1

        # Apply text replacements (reverse order to preserve offsets)
        for region in page_regions_for_text:
            if region.action == RegionAction.REMOVE:
                page_text = (
                    page_text[:region.char_start]
                    + "[REDACTED]"
                    + page_text[region.char_end:]
                )
            elif region.action == RegionAction.TOKENIZE:
                # Find the latest token for this region's text
                # (simplification — in practice we'd track the mapping)
                tokens = vault.list_tokens(source_document=doc.original_filename)
                for t in tokens:
                    if t.original_text == region.text:
                        page_text = (
                            page_text[:region.char_start]
                            + t.token_string
                            + page_text[region.char_end:]
                        )
                        break

        text_lines.append(f"--- Page {page.page_number} ---")
        text_lines.append(page_text)
        text_lines.append("")

        anonymized_pages.append(img)

    # Generate output files
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = Path(doc.original_filename).stem
    output_dir = config.temp_dir / doc.doc_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # PDF output
    pdf_path = output_dir / f"{stem}_anonymized_{timestamp}.pdf"
    _save_images_as_pdf(anonymized_pages, pdf_path)

    # Text output
    text_path = output_dir / f"{stem}_anonymized_{timestamp}.txt"
    text_path.write_text("\n".join(text_lines), encoding="utf-8")

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
        output_pdf_path=str(pdf_path),
        output_text_path=str(text_path),
        tokens_created=tokens_created,
        regions_removed=regions_removed,
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


def _save_images_as_pdf(images: list[Image.Image], output_path: Path) -> None:
    """Save a list of PIL images as a multi-page PDF."""
    if not images:
        return

    # Convert all to RGB (PDF doesn't support RGBA)
    rgb_images = [img.convert("RGB") for img in images]

    rgb_images[0].save(
        str(output_path),
        "PDF",
        save_all=True,
        append_images=rgb_images[1:] if len(rgb_images) > 1 else [],
        resolution=config.render_dpi,
    )
    logger.info(f"Saved anonymized PDF: {output_path}")
