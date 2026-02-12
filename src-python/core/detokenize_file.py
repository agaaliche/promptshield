"""File-based de-tokenization — replace tokens in .pdf, .docx, .xlsx, .txt files.

Reads the file, runs vault.resolve_all_tokens() on extracted text,
writes a new file with tokens replaced, and returns its path.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from typing import Callable

import fitz  # PyMuPDF

from core.config import config

logger = logging.getLogger(__name__)

# Supported MIME → extension mapping
_MIME_MAP: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/plain": ".txt",
    "text/csv": ".csv",
}


def _suffix_from_filename(filename: str) -> str:
    return Path(filename).suffix.lower()


# ---------------------------------------------------------------------------
# Per-format handlers
# ---------------------------------------------------------------------------

def _detokenize_txt(data: bytes, vault) -> tuple[bytes, int, list[str]]:
    """Plain text / CSV — straightforward string replace."""
    text = data.decode("utf-8", errors="replace")
    result, count, unresolved = vault.resolve_all_tokens(text)
    return result.encode("utf-8"), count, unresolved


def _detokenize_docx(data: bytes, vault) -> tuple[bytes, int, list[str]]:
    """DOCX — iterate over paragraphs, tables, headers/footers."""
    from docx import Document

    doc = Document(io.BytesIO(data))
    total_replaced = 0
    all_unresolved: list[str] = []

    def _process(text: str) -> str:
        nonlocal total_replaced, all_unresolved
        result, count, unresolved = vault.resolve_all_tokens(text)
        total_replaced += count
        all_unresolved.extend(unresolved)
        return result

    # Paragraphs
    for para in doc.paragraphs:
        for run in para.runs:
            if run.text:
                run.text = _process(run.text)

    # Tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        if run.text:
                            run.text = _process(run.text)

    # Headers & footers
    for section in doc.sections:
        for header_footer in (section.header, section.footer):
            if header_footer and header_footer.is_linked_to_previous is False:
                for para in header_footer.paragraphs:
                    for run in para.runs:
                        if run.text:
                            run.text = _process(run.text)

    buf = io.BytesIO()
    doc.save(buf)
    # Deduplicate unresolved
    return buf.getvalue(), total_replaced, list(set(all_unresolved))


def _detokenize_xlsx(data: bytes, vault) -> tuple[bytes, int, list[str]]:
    """XLSX — iterate over all cells in all sheets."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data))
    total_replaced = 0
    all_unresolved: list[str] = []

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value:
                    result, count, unresolved = vault.resolve_all_tokens(cell.value)
                    if count > 0:
                        cell.value = result
                        total_replaced += count
                        all_unresolved.extend(unresolved)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), total_replaced, list(set(all_unresolved))


def _detokenize_pdf(data: bytes, vault) -> tuple[bytes, int, list[str]]:
    """PDF — in-place token replacement preserving original layout.

    Strategy: search for each token string on each page using PyMuPDF's
    ``search_for`` (which returns exact pixel rects), add a redaction
    annotation with the original text as replacement, then apply
    redactions.  This preserves all non-token content, images, and
    formatting.
    """
    import re

    pdf_doc = fitz.open(stream=data, filetype="pdf")

    total_replaced = 0
    all_unresolved: list[str] = []

    try:
        # First pass: collect all unique token strings from the document
        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text() + "\n"

        # Find token-shaped strings — supports both compact [P38291] and
        # legacy [ANON_TYPE_HEX] formats.
        token_pattern = re.compile(
            r"\[[A-Z]\d{5}\]"
            r"|\[[A-Z][A-Z0-9_]{4,40}\]"
        )
        found_tokens = set(token_pattern.findall(full_text))

        if not found_tokens:
            # No tokens found — return as-is
            return data, 0, []

        # Resolve each token via the vault
        token_map: dict[str, str] = {}  # token_string → original_text
        for token_str in found_tokens:
            mapping = vault.resolve_token(token_str)
            if mapping:
                token_map[token_str] = mapping.original_text
            else:
                all_unresolved.append(token_str)

        if not token_map:
            return data, 0, list(set(all_unresolved))

        # Second pass: search-and-replace on each page
        for page in pdf_doc:
            for token_str, original_text in token_map.items():
                rects = page.search_for(token_str)
                if not rects:
                    continue

                for rect in rects:
                    # Estimate font size from rect height (rough but effective)
                    fontsize = max(6.0, min(rect.height * 0.85, 14.0))

                    page.add_redact_annot(
                        rect,
                        text=original_text,
                        fill=(1, 1, 1),       # white background
                        text_color=(0, 0, 0),  # black text
                        fontsize=fontsize,
                        fontname="helv",
                    )
                    total_replaced += 1

            page.apply_redactions()

        output_bytes = pdf_doc.tobytes(deflate=True, clean=True)
        return output_bytes, total_replaced, list(set(all_unresolved))

    finally:
        pdf_doc.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Callable] = {
    ".txt":  _detokenize_txt,
    ".csv":  _detokenize_txt,
    ".docx": _detokenize_docx,
    ".xlsx": _detokenize_xlsx,
    ".pdf":  _detokenize_pdf,
}

SUPPORTED_EXTENSIONS = set(_HANDLERS.keys())


def detokenize_file(
    file_data: bytes,
    filename: str,
    vault,
) -> tuple[bytes, str, int, list[str]]:
    """
    De-tokenize tokens inside a file.

    Args:
        file_data: Raw file bytes.
        filename: Original filename (used to detect format).
        vault: Unlocked TokenVault instance.

    Returns:
        (output_bytes, output_filename, tokens_replaced, unresolved_tokens)
    """
    ext = _suffix_from_filename(filename)

    if ext == ".doc":
        raise ValueError(
            "Legacy .doc format is not supported. "
            "Please convert to .docx first (File → Save As in Word)."
        )
    if ext == ".xls":
        raise ValueError(
            "Legacy .xls format is not supported. "
            "Please convert to .xlsx first (File → Save As in Excel)."
        )

    handler = _HANDLERS.get(ext)
    if handler is None:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    output_data, count, unresolved = handler(file_data, vault)

    stem = Path(filename).stem
    out_name = f"{stem}_detokenized{ext}"

    logger.info(
        f"File de-tokenization: {filename} → {out_name}, "
        f"{count} token(s) replaced, {len(unresolved)} unresolved"
    )
    return output_data, out_name, count, unresolved
