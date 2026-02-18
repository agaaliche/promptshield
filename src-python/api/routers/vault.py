"""Vault lifecycle: unlock, status, stats, tokens, export, import."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _PydanticBaseModel

from models.schemas import VaultStatsResponse, VaultUnlockResponse, VaultStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["vault"])

# ── Rate-limiting state for vault unlock ──────────────────────────
_MAX_UNLOCK_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60
# M6: Use a threading.Lock to protect the rate-limit list from concurrent access
import threading
_unlock_lock = threading.Lock()
_unlock_attempts: list[float] = []  # timestamps of recent failures


class _PassphraseBody(_PydanticBaseModel):
    passphrase: str


def _check_unlock_rate_limit() -> None:
    """Raise 429 if too many failed unlock attempts within the lockout window."""
    now = time.monotonic()
    with _unlock_lock:
        # Prune old entries outside the window
        while _unlock_attempts and now - _unlock_attempts[0] > _LOCKOUT_SECONDS:
            _unlock_attempts.pop(0)
        if len(_unlock_attempts) >= _MAX_UNLOCK_ATTEMPTS:
            wait = int(_LOCKOUT_SECONDS - (now - _unlock_attempts[0])) + 1
            raise HTTPException(
                429,
                f"Too many unlock attempts. Try again in {wait}s.",
            )


@router.post("/vault/unlock", response_model=VaultUnlockResponse)
async def unlock_vault(body: _PassphraseBody) -> VaultUnlockResponse:
    """Unlock the token vault with a passphrase."""
    from core.vault.store import vault

    _check_unlock_rate_limit()

    try:
        vault.initialize(body.passphrase)
        # Success — clear failure history
        with _unlock_lock:
            _unlock_attempts.clear()
        return VaultUnlockResponse(status="ok", message="Vault unlocked")
    except ValueError as e:
        with _unlock_lock:
            _unlock_attempts.append(time.monotonic())
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, "Failed to open vault. Check server logs for details.")


@router.get("/vault/status", response_model=VaultStatusResponse)
async def vault_status() -> VaultStatusResponse:
    """Check vault status."""
    from core.vault.store import vault
    return VaultStatusResponse(unlocked=vault.is_unlocked)


@router.get("/vault/stats", response_model=VaultStatsResponse)
async def vault_stats() -> VaultStatsResponse:
    """Get vault statistics."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    stats = await asyncio.to_thread(vault.get_stats)
    return VaultStatsResponse(**stats)


@router.get("/vault/tokens")
async def list_vault_tokens(
    source_document: str | None = None,
    offset: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """List tokens in the vault with pagination."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    # M5: Pagination support
    if limit > 1000:
        limit = 1000
    tokens = await asyncio.to_thread(vault.list_tokens, source_document=source_document)
    total = len(tokens)
    page = tokens[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "tokens": [t.model_dump(mode="json") for t in page],
    }


@router.post("/vault/export")
async def export_vault(body: _PassphraseBody) -> JSONResponse:
    """Export all vault tokens as encrypted JSON."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    try:
        data = vault.export_vault(body.passphrase)
        return JSONResponse(content={"export": data})
    except Exception as e:
        logger.error(f"Vault export failed: {e}")
        raise HTTPException(500, "Export failed. Check server logs for details.")


class _VaultImportBody(_PydanticBaseModel):
    export_data: str
    passphrase: str


@router.post("/vault/import")
async def import_vault(body: _VaultImportBody) -> JSONResponse:
    """Import tokens from an encrypted vault backup."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    try:
        result = vault.import_vault(body.export_data, body.passphrase)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, "Import failed. Check server logs for details.")
