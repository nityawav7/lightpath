"""Small in-memory sliding-window rate limiter for mutating API calls.

Good enough for a single-instance deployment; a multi-instance deployment
would move this to Redis or the API gateway.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, per_minute: int) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.per_minute <= 0 or request.method not in MUTATING:
            return await call_next(request)
        now = time.monotonic()
        hits = self._hits[self._client_ip(request)]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            retry = int(60 - (now - hits[0])) + 1
            return JSONResponse(
                {"detail": "rate limit exceeded, slow down"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under abuse
            self._hits.clear()
        return await call_next(request)
