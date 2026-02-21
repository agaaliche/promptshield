"""Vault lifecycle: status, stats, tokens, export, import.

The vault no longer requires a passphrase — it auto-initialises on first
access and stores token mappings in plaintext SQLite.  The ``/vault/unlock``
endpoint is kept as a no-op for backward compatibility with older frontends.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _PydanticBaseModel

from models.schemas import VaultStatsResponse, VaultUnlockResponse, VaultStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["vault"])


class _PassphraseBody(_PydanticBaseModel):
    passphrase: str = ""


@router.post("/vault/unlock", response_model=VaultUnlockResponse)
async def unlock_vault(body: _PassphraseBody | None = None) -> VaultUnlockResponse:
    """No-op kept for backward compatibility — vault auto-initialises."""
    from core.vault.store import vault
    vault.ensure_ready()
    return VaultUnlockResponse(status="ok", message="Vault ready")


@router.get("/vault/status", response_model=VaultStatusResponse)
async def vault_status() -> VaultStatusResponse:
    """Check vault status (always unlocked after first access)."""
    from core.vault.store import vault
    vault.ensure_ready()
    return VaultStatusResponse(unlocked=vault.is_unlocked)


@router.get("/vault/stats", response_model=VaultStatsResponse)
async def vault_stats() -> VaultStatsResponse:
    """Get vault statistics."""
    from core.vault.store import vault
    vault.ensure_ready()
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
    vault.ensure_ready()
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
async def export_vault() -> JSONResponse:
    """Export all vault tokens as JSON."""
    from core.vault.store import vault
    vault.ensure_ready()
    try:
        data = vault.export_vault()
        return JSONResponse(content={"export": data})
    except Exception as e:
        logger.error(f"Vault export failed: {e}")
        raise HTTPException(500, "Export failed. Check server logs for details.")


class _VaultImportBody(_PydanticBaseModel):
    export_data: str


@router.post("/vault/import")
async def import_vault(body: _VaultImportBody) -> JSONResponse:
    """Import tokens from a vault backup JSON."""
    from core.vault.store import vault
    vault.ensure_ready()
    try:
        result = vault.import_vault(body.export_data)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, "Import failed. Check server logs for details.")
