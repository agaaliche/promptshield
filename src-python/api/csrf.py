"""CSRF protection middleware for the FastAPI sidecar.

Requires a custom ``X-Requested-With`` header on all state-mutating
requests (POST, PUT, PATCH, DELETE).  Browsers block cross-origin
requests with custom headers via CORS preflight, so a malicious page
cannot forge the header.

GET/HEAD/OPTIONS are exempt (safe methods).
``/health`` and the Stripe-style webhook paths are also exempt.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Methods that are safe (read-only) and don't need CSRF protection
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths exempt from CSRF checks (webhooks use their own signature verification)
_EXEMPT_PREFIXES = (
    "/health",
    "/api/warmup",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject state-mutating requests that lack the ``X-Requested-With`` header.

    This is a simple, widely-used CSRF mitigation: the frontend sets
    ``X-Requested-With: XMLHttpRequest`` (or any non-empty value) on
    every fetch/XHR call.  Since custom headers trigger a CORS preflight,
    a cross-origin attacker cannot include them.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        method = request.method.upper()

        # Safe methods are always allowed
        if method in _SAFE_METHODS:
            return await call_next(request)

        # Exempt paths
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Require the custom header
        if not request.headers.get("x-requested-with"):
            logger.warning(
                "CSRF: Blocked %s %s — missing X-Requested-With header (origin=%s)",
                method, path, request.headers.get("origin", "unknown"),
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Missing X-Requested-With header"},
            )

        return await call_next(request)
