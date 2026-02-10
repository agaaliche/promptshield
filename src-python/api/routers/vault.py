"""Vault lifecycle: unlock, status, stats, tokens, export, import."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel as _PydanticBaseModel

from models.schemas import VaultStatsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["vault"])


class _PassphraseBody(_PydanticBaseModel):
    passphrase: str


@router.post("/vault/unlock")
async def unlock_vault(body: _PassphraseBody):
    """Unlock the token vault with a passphrase."""
    from core.vault.store import vault

    try:
        vault.initialize(body.passphrase)
        return {"status": "ok", "message": "Vault unlocked"}
    except ValueError as e:
        raise HTTPException(403, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to open vault: {e}")


@router.get("/vault/status")
async def vault_status():
    """Check vault status."""
    from core.vault.store import vault
    return {
        "unlocked": vault.is_unlocked,
        "path": str(vault.db_path),
    }


@router.get("/vault/stats", response_model=VaultStatsResponse)
async def vault_stats():
    """Get vault statistics."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    stats = vault.get_stats()
    return VaultStatsResponse(**stats)


@router.get("/vault/tokens")
async def list_vault_tokens(source_document: str | None = None):
    """List all tokens in the vault."""
    from core.vault.store import vault
    if not vault.is_unlocked:
        raise HTTPException(403, "Vault is locked")
    tokens = vault.list_tokens(source_document=source_document)
    return [t.model_dump(mode="json") for t in tokens]


@router.post("/vault/export")
async def export_vault(body: _PassphraseBody):
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
async def import_vault(body: _VaultImportBody):
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
        raise HTTPException(500, f"Import failed: {e}")
