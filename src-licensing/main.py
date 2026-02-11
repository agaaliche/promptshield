"""PromptShield Licensing Server — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine
from models import Base

logger = logging.getLogger("licensing")


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",   # Tauri dev
        "http://localhost:5173",   # Vite dev
        "https://promptshield.com",
        "https://www.promptshield.com",
        "https://app.promptshield.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
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

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8443,
        reload=True,
        log_level="info",
    )
