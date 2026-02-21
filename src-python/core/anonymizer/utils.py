"""Common utilities for anonymization handlers.

This module contains shared helper functions used by all file-type handlers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import config
from core.vault.store import vault
from models.schemas import AnonymizeResponse, DocumentInfo

logger = logging.getLogger(__name__)

# File type constants
PDF_TYPES = {"application/pdf"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp"}
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def save_manifest(
    output_dir: Path,
    doc_id: str,
    original_filename: str,
    token_manifest: list[dict],
) -> None:
    """Save the token manifest as plaintext JSON alongside the output."""
    manifest = {
        "doc_id": doc_id,
        "original_filename": original_filename,
        "tokens": token_manifest,
    }
    manifest_path = output_dir / "token_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info(f"Saved token manifest with {len(token_manifest)} entries")


def finalize_anonymization(
    doc: DocumentInfo,
    output_path: Path,
    tokens_created: int,
    regions_removed: int,
    output_format: str,
) -> AnonymizeResponse:
    """Build the final response after anonymization completes.

    Args:
        doc: The document that was anonymized
        output_path: Path to the anonymized output file
        tokens_created: Number of PII tokens created
        regions_removed: Number of regions completely removed
        output_format: File extension of the output (e.g., "pdf", "docx")

    Returns:
        AnonymizeResponse with all relevant metadata
    """
    return AnonymizeResponse(
        doc_id=doc.doc_id,
        output_path=str(output_path),
        output_format=output_format,
        tokens_created=tokens_created,
        regions_removed=regions_removed,
        timestamp=datetime.utcnow().isoformat(),
    )


def get_context_snippet(text: str, start: int, end: int, context_chars: int = 50) -> str:
    """Extract a snippet of text around a region for logging/debugging.

    Args:
        text: The full text
        start: Start offset of the region
        end: End offset of the region
        context_chars: Number of characters of context on each side

    Returns:
        Snippet with [...] markers for truncation
    """
    snippet_start = max(0, start - context_chars)
    snippet_end = min(len(text), end + context_chars)

    prefix = "..." if snippet_start > 0 else ""
    suffix = "..." if snippet_end < len(text) else ""

    return f"{prefix}{text[snippet_start:snippet_end]}{suffix}"
