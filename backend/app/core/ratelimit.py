"""In-process sliding-window rate limiter + ASGI middleware.

Keyed by client identity (IP) so a single client cannot exhaust the API. The
limiter core is pure and clock-injectable for deterministic tests; the
middleware applies it to /api/v1 mutating traffic and returns 429 + Retry-After.
For multi-replica deployments this backs onto Redis (same interface) — see
docs/02 §4.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiter:
    def __init__(self, limit: int = 120, window_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> Tuple[bool, float]:
        """Returns (allowed, retry_after_seconds). Evicts timestamps older than
        the window, then admits if under the limit."""
        now = self.clock()
        dq = self._hits[key]
        cutoff = now - self.window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self.limit:
            retry = self.window_s - (now - dq[0])
            return False, max(0.0, retry)
        dq.append(now)
        return True, 0.0


class RateLimitMiddleware:
    """Pure-ASGI middleware. Limits state-changing requests to the API surface;
    read-only GETs, health and metrics are exempt so scrapers/dashboards are
    never throttled."""

    EXEMPT_PREFIXES = ("/health", "/metrics", "/docs", "/openapi", "/ws")

    def __init__(self, app, limiter: RateLimiter):
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = request.url.path
        method = request.method
        if method in ("GET", "HEAD", "OPTIONS") or path.startswith(self.EXEMPT_PREFIXES):
            return await self.app(scope, receive, send)

        client = request.client.host if request.client else "unknown"
        allowed, retry = self.limiter.check(client)
        if not allowed:
            resp = JSONResponse(
                {"error": {"code": "rate_limited",
                           "message": "too many requests; slow down"}},
                status_code=429, headers={"Retry-After": str(int(retry) + 1)})
            return await resp(scope, receive, send)
        return await self.app(scope, receive, send)
