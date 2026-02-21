"""Text and file de-tokenization endpoints."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from core.config import config
from models.schemas import (
    DetokenizeRequest,
    DetokenizeResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["detokenize"])


@router.post("/detokenize", response_model=DetokenizeResponse)
async def detokenize(req: DetokenizeRequest) -> DetokenizeResponse:
    """Replace tokens in text with their original values."""
    from core.vault.store import vault
    vault.ensure_ready()

    result_text, count, unresolved = await asyncio.to_thread(
        vault.resolve_all_tokens, req.text
    )
    return DetokenizeResponse(
        original_text=result_text,
        tokens_replaced=count,
        unresolved_tokens=unresolved,
    )


@router.post("/detokenize/file")
async def detokenize_file_endpoint(file: UploadFile = File(...)) -> FileResponse:
    """De-tokenize tokens inside an uploaded file (.docx, .xlsx, .pdf, .txt, .csv)."""
    from core.vault.store import vault
    from core.detokenize_file import detokenize_file, SUPPORTED_EXTENSIONS

    vault.ensure_ready()

    filename = file.filename or "unknown.txt"

    # M11: Enforce max upload size (100 MB)
    _MAX_FILE_SIZE = 100 * 1024 * 1024
    data = await file.read()
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {_MAX_FILE_SIZE // (1024*1024)} MB.")

    try:
        out_bytes, out_name, count, unresolved = detokenize_file(data, filename, vault)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"File de-tokenization failed: {e}")
        raise HTTPException(500, "De-tokenization failed. Check server logs for details.")

    ext = Path(out_name).suffix.lower()
    media_types = {
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    import tempfile
    tmp = Path(tempfile.mkdtemp(dir=str(config.temp_dir)))
    out_path = tmp / out_name
    out_path.write_bytes(out_bytes)

    def _cleanup() -> None:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

    headers = {
        "X-Tokens-Replaced": str(count),
        "X-Unresolved-Tokens": ",".join(unresolved) if unresolved else "",
        "Access-Control-Expose-Headers": "X-Tokens-Replaced, X-Unresolved-Tokens",
    }

    return FileResponse(
        str(out_path),
        media_type=media_type,
        filename=out_name,
        headers=headers,
        background=BackgroundTask(_cleanup),
    )
