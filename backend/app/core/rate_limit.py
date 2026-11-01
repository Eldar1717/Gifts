"""In-process sliding-window rate limiter.

Suitable for a single API instance. For horizontal scaling switch the store to
Redis (the ``RateLimiter`` interface is intentionally tiny). The limiter is a
defence-in-depth layer, not a replacement for platform-level throttling.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:  # pragma: no cover - test helper
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def _parse(rule: str, fallback: tuple[int, int]) -> tuple[int, int]:
    try:
        limit, window = rule.split("/")
        return max(1, int(limit)), max(1, int(window))
    except (ValueError, AttributeError):
        return fallback


def rate_limit(rule: str):
    """FastAPI dependency factory, e.g. ``Depends(rate_limit('15/60'))``."""

    limit, window = _parse(rule, (60, 60))

    async def dependency(request: Request) -> None:
        # Key by Telegram user when available, otherwise by client IP + path.
        identity = request.headers.get("x-dev-telegram-id") or ""
        auth = request.headers.get("authorization", "")
        if auth.startswith("tma "):
            # A short, stable suffix is enough for bucketing; initData is signed.
            identity = auth[-16:] + auth[10:26]
        client = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{identity or client}"
        if request.url.path.startswith("/api/admin"):
            key = f"admin:{request.url.path}:{identity or client}"
        if not limiter.check(key, limit, window):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, slow down and try again shortly",
                headers={"Retry-After": str(window)},
            )

    return dependency


AUTH_LIMIT = rate_limit(settings.rate_limit_auth)
READ_LIMIT = rate_limit(settings.rate_limit_read)
WRITE_LIMIT = rate_limit(settings.rate_limit_write)
CHECKOUT_LIMIT = rate_limit(settings.rate_limit_checkout)
