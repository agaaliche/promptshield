"""FastAPI application — main API for the promptShield sidecar."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.config import config
from core.persistence import DocumentStore
from api import deps
from api.routers import (
    documents,
    detection,
    regions,
    anonymize,
    detokenize,
    vault,
    llm,
    settings,
)

logger = logging.getLogger(__name__)

# L1: Single source of truth for the app version
_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Lifecycle — replaces deprecated on_event("startup") / on_event("shutdown")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup → yield → shutdown."""
    logger.info("Starting promptShield sidecar...")

    # Initialize document store
    storage_dir = config.data_dir / "storage"
    deps.store = DocumentStore(storage_dir)

    # Load existing documents from storage
    try:
        loaded = deps.store.load_all_documents()
        # Mutate the existing dict in-place so that all routers (which
        # imported `documents` by reference at module load) see the data.
        deps.documents.clear()
        deps.documents.update(loaded)
        logger.info(f"Loaded {len(deps.documents)} existing documents")
    except Exception as e:
        # L6: Log the error but don't wipe all documents — individual
        # corrupt files are already skipped inside load_all_documents.
        logger.error(f"Failed to load documents: {e}")

    # Mount temp dir for serving page bitmaps (legacy support)
    config.temp_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/bitmaps",
        StaticFiles(directory=str(config.temp_dir)),
        name="bitmaps",
    )

    # Also mount persistent storage bitmaps
    app.mount(
        "/storage-bitmaps",
        StaticFiles(directory=str(deps.store.bitmaps_dir)),
        name="storage-bitmaps",
    )
    logger.info(f"Serving bitmaps from {config.temp_dir} (temp) and {deps.store.bitmaps_dir} (persistent)")

    # Auto-load LLM model if enabled
    if config.auto_load_llm:
        # Configure remote LLM engine if settings exist
        if config.llm_api_url and config.llm_api_key and config.llm_api_model:
            try:
                from core.llm.remote_engine import remote_llm_engine
                remote_llm_engine.configure(config.llm_api_url, config.llm_api_key, config.llm_api_model)
                logger.info(f"Remote LLM configured: {config.llm_api_model} at {config.llm_api_url}")
            except Exception as e:
                logger.warning(f"Failed to configure remote LLM (non-fatal): {e}")

        # Also load local model (available as fallback or when provider=local)
        try:
            from core.llm.engine import llm_engine

            model_path: str | None = None

            if config.llm_model_path and Path(config.llm_model_path).exists():
                model_path = config.llm_model_path
                logger.info(f"Auto-loading user-preferred LLM: {Path(model_path).name}")

            if not model_path:
                gguf_files = sorted(config.models_dir.glob("*.gguf"))
                qwen = sorted(
                    [f for f in gguf_files if "qwen" in f.stem.lower()],
                    key=lambda f: f.stat().st_size,
                )
                if qwen:
                    model_path = str(qwen[0])
                elif gguf_files:
                    model_path = str(gguf_files[0])

            if model_path:
                logger.info(f"Auto-loading LLM model: {Path(model_path).name}")
                llm_engine.load_model(model_path)
                logger.info("LLM model loaded successfully")
            else:
                logger.info("No GGUF models found — skipping auto-load")
        except Exception as e:
            logger.warning(f"Auto-load LLM failed (non-fatal): {e}")

    yield  # ── app runs here ──

    # Shutdown cleanup
    logger.info("Shutting down promptShield sidecar...")

    # Close the vault SQLite connection
    try:
        from core.vault.store import vault
        vault.close()
        logger.info("Vault connection closed")
    except Exception as e:
        logger.warning(f"Failed to close vault: {e}")

    # Clean up temp directory (stale bitmaps, output files)
    try:
        import shutil
        if config.temp_dir.exists():
            shutil.rmtree(config.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned temp directory: {config.temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to clean temp dir: {e}")


app = FastAPI(
    title="promptShield",
    version=_VERSION,
    description="Offline document anonymizer with local LLM — promptShield",
    lifespan=lifespan,
)

# CORS — allow Tauri webview and local dev server
_ALLOWED_ORIGINS = [
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "tauri://localhost",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    # M7: Only allow methods the API actually uses
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------
app.include_router(documents.router)
app.include_router(detection.router)
app.include_router(regions.router)
app.include_router(anonymize.router)
app.include_router(detokenize.router)
app.include_router(vault.router)
app.include_router(llm.router)
app.include_router(settings.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": _VERSION}


# ---------------------------------------------------------------------------
# Bundled frontend — serve the React SPA when running as a standalone exe
# ---------------------------------------------------------------------------

def _get_frontend_dir() -> Path | None:
    """Locate the bundled frontend dist directory."""
    if getattr(sys, "frozen", False):
        candidate = Path(sys._MEIPASS) / "frontend_dist"     # type: ignore[attr-defined]
        if candidate.is_dir():
            return candidate
    candidate = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if candidate.is_dir():
        return candidate
    return None


_frontend_dir = _get_frontend_dir()

if _frontend_dir is not None:
    app.mount(
        "/assets",
        StaticFiles(directory=str(_frontend_dir / "assets")),
        name="frontend-assets",
    )

    @app.get("/")
    async def serve_index():
        return HTMLResponse((_frontend_dir / "index.html").read_text(encoding="utf-8"))

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "health", "bitmaps/")):
            raise HTTPException(404)
        file_path = (_frontend_dir / full_path).resolve()
        # Prevent path traversal — ensure resolved path is within frontend dir
        if not file_path.is_relative_to(_frontend_dir.resolve()):
            raise HTTPException(404)
        if file_path.is_file():
            return FileResponse(str(file_path))
        return HTMLResponse((_frontend_dir / "index.html").read_text(encoding="utf-8"))
