"""PromptShield Licensing Server — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select

from config import settings, validate_settings
from database import engine, async_session
from models import Base, LicenseKey
from rate_limit import RateLimitMiddleware

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

    # S7: Background task — clean up expired/revoked license keys every 6 hours
    async def _cleanup_old_keys():
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # every 6 hours
                cutoff = datetime.now(timezone.utc) - timedelta(days=90)
                async with async_session() as db:
                    result = await db.execute(
                        delete(LicenseKey).where(
                            LicenseKey.expires_at < cutoff,
                        )
                    )
                    await db.commit()
                    if result.rowcount:
                        logger.info("Cleaned up %d expired license keys older than 90 days", result.rowcount)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("License key cleanup failed")

    cleanup_task = asyncio.create_task(_cleanup_old_keys())

    yield

    cleanup_task.cancel()
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
    "http://localhost:5173",        # Vite dev server
    "http://localhost:1420",        # Tauri dev server
]

# M14: Only add dev origins when explicitly in dev mode
if settings.dev_mode:
    _LICENSING_ALLOWED_ORIGINS.extend([
        "http://localhost:3000",    # Next.js dev (website)
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_LICENSING_ALLOWED_ORIGINS,
    allow_credentials=True,
    # M7: Only allow methods the API uses
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# S4: Rate limiting — 60 requests/minute per IP
app.add_middleware(RateLimitMiddleware, max_requests=60, window=60)

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
    try:
        async with async_session() as session:
            await session.execute(select(1))
    except Exception:
        return {"status": "degraded", "db": "unreachable", "version": "1.0.0"}
    return {"status": "ok", "db": "connected", "version": "1.0.0"}


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
