"""PromptShield Licensing Server — FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings, validate_settings
from database import engine
from models import Base

logger = logging.getLogger("licensing")

# Validate configuration on import (before server starts)
validate_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables (dev only), shutdown: dispose engine."""
    # In production, use Alembic migrations instead.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Licensing server started")
    yield
    await engine.dispose()
    logger.info("Licensing server stopped")


app = FastAPI(
    title="PromptShield Licensing API",
    version="1.0.0",
    description="License management, authentication, and billing for PromptShield desktop app.",
    lifespan=lifespan,
)

# CORS — allow desktop app and web dashboard
_LICENSING_ALLOWED_ORIGINS = [
    "https://promptshield.com",
    "https://www.promptshield.com",
    "https://app.promptshield.com",
    "https://tauri.localhost",      # Tauri desktop (Windows)
    "tauri://localhost",            # Tauri desktop (macOS/Linux)
    "http://localhost:8910",        # Standalone binary
]

# M14: Only add dev origins when explicitly in dev mode
if settings.dev_mode:
    _LICENSING_ALLOWED_ORIGINS.extend([
        "http://localhost:1420",   # Tauri dev
        "http://localhost:5173",   # Vite dev
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_LICENSING_ALLOWED_ORIGINS,
    allow_credentials=True,
    # M7: Only allow methods the API uses
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Register routers ────────────────────────────────────────────

from routers.auth import router as auth_router       # noqa: E402
from routers.license import router as license_router  # noqa: E402
from routers.billing import router as billing_router  # noqa: E402
from routers.admin import router as admin_router      # noqa: E402

app.include_router(auth_router)
app.include_router(license_router)
app.include_router(billing_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Logging ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)

if __name__ == "__main__":
    import uvicorn

    # M13: Never use reload=True in production; use an env var to control
    is_dev = settings.dev_mode

    # H6: In production, configure SSL cert/key via environment variables
    ssl_kwargs: dict[str, Any] = {}
    ssl_cert = os.environ.get("PS_SSL_CERTFILE")
    ssl_key = os.environ.get("PS_SSL_KEYFILE")
    if ssl_cert and ssl_key:
        ssl_kwargs["ssl_certfile"] = ssl_cert
        ssl_kwargs["ssl_keyfile"] = ssl_key

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8443,
        reload=is_dev,
        log_level="info",
        **ssl_kwargs,
    )
