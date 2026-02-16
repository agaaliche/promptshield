"""Lightweight in-memory rate-limiting middleware for FastAPI.

Uses a sliding-window counter per client IP.  No external dependencies.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default: 600 requests per 60-second window per client IP
# The frontend fires many parallel requests during multi-file upload
# (document metadata, regions, detection-progress polling, status checks).
_DEFAULT_RATE = 600
_DEFAULT_WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter per client IP.

    Paths starting with ``/health`` or ``/bitmaps`` are exempt so they
    don't burn quota.

    Args:
        app: The ASGI application.
        max_requests: Maximum requests allowed within *window_seconds*.
        window_seconds: Length of the sliding window.
    """

    _EXEMPT_PREFIXES = (
        "/health",
        "/bitmaps/",
        "/storage-bitmaps/",
        "/assets/",
        "/api/warmup",
        "/api/llm/status",
        "/api/vault/status",
        "/api/settings",
    )
    # Also exempt high-frequency polling suffixes checked per-path
    _EXEMPT_SUFFIXES = (
        "/detection-progress",
        "/regions",
    )

    def __init__(
        self,
        app: Any,
        max_requests: int = _DEFAULT_RATE,
        window_seconds: int = _DEFAULT_WINDOW,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # IP → deque of request timestamps (O(1) popleft vs O(n) list.pop(0))
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    # ------------------------------------------------------------------

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        """Check rate limit before forwarding the request."""
        path = request.url.path
        if (any(path.startswith(p) for p in self._EXEMPT_PREFIXES)
                or any(path.endswith(s) for s in self._EXEMPT_SUFFIXES)):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Prune old entries and count
        hits = self._hits[client_ip]
        # Remove timestamps outside the window
        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self.max_requests:
            retry_after = int(hits[0] - window_start) + 1
            logger.warning(
                "Rate limit exceeded for %s (%d/%d in %ds window)",
                client_ip, len(hits), self.max_requests, self.window_seconds,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Try again in {retry_after}s."},
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
