"""LLM model management: status, load/unload, remote configuration."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel as _PydanticBaseModel

from core.config import config
from models.schemas import LLMStatusResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["llm"])


@router.get("/llm/status", response_model=LLMStatusResponse)
async def llm_status():
    """Get LLM engine status."""
    from core.llm.engine import llm_engine
    from core.llm.remote_engine import remote_llm_engine

    return LLMStatusResponse(
        loaded=llm_engine.is_loaded() or remote_llm_engine.is_loaded(),
        model_name=(
            remote_llm_engine.model_name
            if config.llm_provider == "remote" and remote_llm_engine.is_loaded()
            else llm_engine.model_name
        ),
        model_path=(
            remote_llm_engine.model_path
            if config.llm_provider == "remote" and remote_llm_engine.is_loaded()
            else llm_engine.model_path
        ),
        gpu_enabled=llm_engine.gpu_enabled,
        context_size=config.llm_context_size,
        provider=config.llm_provider,
        remote_api_url=config.llm_api_url,
        remote_model=config.llm_api_model,
    )


@router.post("/llm/load")
async def load_llm(model_path: str, force_cpu: bool = False):
    """Load a GGUF model and save the choice for future auto-load."""
    from core.llm.engine import llm_engine
    try:
        llm_engine.load_model(model_path, force_cpu=force_cpu)
        config.llm_model_path = model_path
        config.llm_provider = "local"
        config.save_user_settings()
        return {"status": "ok", "model": llm_engine.model_name}
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {e}")


@router.post("/llm/unload")
async def unload_llm():
    """Unload the current LLM model."""
    from core.llm.engine import llm_engine
    llm_engine.unload_model()
    return {"status": "ok"}


@router.get("/llm/models")
async def list_models():
    """List available GGUF models in the models directory."""
    from core.llm.engine import llm_engine
    return llm_engine.list_available_models()


class _RemoteLLMConfig(_PydanticBaseModel):
    api_url: str
    api_key: str
    model: str


@router.post("/llm/remote/configure")
async def configure_remote_llm(body: _RemoteLLMConfig):
    """Configure a remote OpenAI-compatible LLM endpoint."""
    from core.llm.remote_engine import remote_llm_engine

    remote_llm_engine.configure(body.api_url, body.api_key, body.model)
    config.llm_provider = "remote"
    config.llm_api_url = body.api_url
    config.llm_api_key = body.api_key
    config.llm_api_model = body.model
    config.save_user_settings()
    return {"status": "ok", "model": body.model, "provider": "remote"}


@router.post("/llm/remote/disconnect")
async def disconnect_remote_llm():
    """Remove remote LLM configuration."""
    from core.llm.remote_engine import remote_llm_engine

    remote_llm_engine.configure("", "", "")
    config.llm_api_url = ""
    config.llm_api_key = ""
    config.llm_api_model = ""
    if config.llm_provider == "remote":
        config.llm_provider = "local"
    config.save_user_settings()
    return {"status": "ok"}


@router.post("/llm/remote/test")
async def test_remote_llm():
    """Test the remote LLM connection with a minimal ping."""
    import asyncio
    from core.llm.remote_engine import remote_llm_engine

    if not remote_llm_engine.is_loaded():
        raise HTTPException(400, "Remote LLM not configured")
    result = await asyncio.get_event_loop().run_in_executor(
        None, remote_llm_engine.test_connection
    )
    return result


@router.post("/llm/provider")
async def set_llm_provider(provider: str):
    """Switch between 'local' and 'remote' LLM provider."""
    if provider not in ("local", "remote"):
        raise HTTPException(400, "provider must be 'local' or 'remote'")
    config.llm_provider = provider
    config.save_user_settings()
    return {"status": "ok", "provider": provider}


@router.post("/llm/open-models-dir")
async def open_models_dir():
    """Open the models directory in the system file explorer."""
    models_dir = config.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(models_dir))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(models_dir)])
        else:
            subprocess.Popen(["xdg-open", str(models_dir)])
        return {"status": "ok", "path": str(models_dir)}
    except Exception as e:
        raise HTTPException(500, f"Failed to open directory: {e}")
