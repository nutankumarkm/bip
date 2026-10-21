"""In-memory token bucket rate limiting for BIP API and Gateway services (M9)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)

    def consume(self, amount: float = 1.0) -> tuple[bool, int]:
        """Attempt to consume `amount` tokens.

        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now

        # Add newly accrued tokens up to capacity
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0

        # Calculate seconds until enough tokens are refilled
        missing = amount - self.tokens
        retry_after = int(missing / self.refill_rate) + 1 if self.refill_rate > 0 else 60
        return False, max(1, retry_after)


class RateLimiter:
    """Thread-safe in-memory rate limiter using the Token Bucket algorithm."""

    def __init__(
        self,
        requests_per_minute: int = 120,
        burst: int = 150,
        cleanup_interval_sec: float = 300.0,
    ) -> None:
        self.rate_per_sec = requests_per_minute / 60.0
        self.capacity = float(burst)
        self.cleanup_interval = cleanup_interval_sec
        self._buckets: dict[str, TokenBucket] = {}
        self._last_cleanup = time.monotonic()
        self._lock = Lock()

    def check(self, key: str, cost: float = 1.0) -> tuple[bool, int]:
        """Check if request for `key` is permitted.

        Returns (is_allowed, retry_after_seconds).
        """
        with self._lock:
            now = time.monotonic()
            if now - self._last_cleanup > self.cleanup_interval:
                self._cleanup(now)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(capacity=self.capacity, refill_rate=self.rate_per_sec)
                self._buckets[key] = bucket

            return bucket.consume(cost)

    def reset(self, key: str | None = None) -> None:
        """Reset limiter state, optionally for a specific key."""
        with self._lock:
            if key is not None:
                self._buckets.pop(key, None)
            else:
                self._buckets.clear()

    def _cleanup(self, now: float) -> None:
        """Evict buckets that are full and idle for > 5 minutes."""
        stale_threshold = 300.0
        keys_to_delete = [
            k
            for k, b in self._buckets.items()
            if (now - b.last_refill > stale_threshold) and (b.tokens >= b.capacity * 0.95)
        ]
        for k in keys_to_delete:
            self._buckets.pop(k, None)
        self._last_cleanup = now


# Default global rate limiter instance
global_rate_limiter = RateLimiter(requests_per_minute=120, burst=150)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI / Starlette middleware enforcing token bucket rate limiting."""

    EXEMPT_PATHS = frozenset(
        {
            "/healthz",
            "/readyz",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
    )

    def __init__(
        self,
        app: Any,
        limiter: RateLimiter | None = None,
        key_func: Callable[[Request], str] | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or global_rate_limiter
        self.key_func = key_func or self._default_key_func
        self.enabled = enabled

    @staticmethod
    def _default_key_func(request: Request) -> str:
        # Prefer client token/ID from Authorization header if present
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            # Rate limit per token prefix (first 20 chars)
            return f"token:{auth[7:27]}"

        # Fallback to client IP
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        elif request.client:
            ip = request.client.host
        else:
            ip = "unknown"
        return f"ip:{ip}"

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Skip exempt paths (health checks, openapi docs)
        path = request.url.path
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        key = self.key_func(request)
        allowed, retry_after = self.limiter.check(key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": f"Too many requests. Please slow down and try again in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(int(self.limiter.capacity)),
                },
            )

        response: Response = await call_next(request)
        return response
