"""Simple in-memory sliding-window rate limiter for the licensing server.

Limits requests per IP address. Uses a per-IP deque of timestamps.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

# ── Configuration ────────────────────────────────────────────────

MAX_REQUESTS = 60       # max requests per window
WINDOW_SECONDS = 60     # sliding window duration in seconds

# Endpoints exempt from rate limiting (health checks, static)
_EXEMPT_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter — per IP, in-memory."""

    def __init__(self, app, max_requests: int = MAX_REQUESTS, window: int = WINDOW_SECONDS):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self.window
        q = self._hits[client_ip]

        # Expire old entries
        while q and q[0] < window_start:
            q.popleft()

        if len(q) >= self.max_requests:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(self.window)},
            )

        q.append(now)
        return await call_next(request)
