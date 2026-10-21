"""Unit tests for in-memory token bucket rate limiting (M9)."""

from __future__ import annotations

import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from bip.core.ratelimit import (
    RateLimiter,
    RateLimitMiddleware,
    TokenBucket,
)


def test_token_bucket_consume_and_depletion() -> None:
    # 2 tokens capacity, refills at 1 token per 10 seconds (0.1/s)
    bucket = TokenBucket(capacity=2.0, refill_rate=0.1)

    # First two requests consume immediately
    allowed1, wait1 = bucket.consume(1.0)
    assert allowed1 is True
    assert wait1 == 0

    allowed2, wait2 = bucket.consume(1.0)
    assert allowed2 is True
    assert wait2 == 0

    # Third request is denied because bucket is empty
    allowed3, wait3 = bucket.consume(1.0)
    assert allowed3 is False
    assert wait3 > 0


def test_token_bucket_refills_over_time() -> None:
    # Capacity 1, refills at 100 tokens per second (fast for test)
    bucket = TokenBucket(capacity=1.0, refill_rate=100.0)

    allowed, _ = bucket.consume(1.0)
    assert allowed is True

    # Empty
    allowed_empty, _ = bucket.consume(1.0)
    assert allowed_empty is False

    # Sleep 20ms -> should refill ~2 tokens (capped at capacity 1.0)
    time.sleep(0.02)
    allowed_refilled, _ = bucket.consume(1.0)
    assert allowed_refilled is True


def test_rate_limiter_distinct_keys() -> None:
    limiter = RateLimiter(requests_per_minute=60, burst=1)

    # Key A consumed
    assert limiter.check("user-a")[0] is True
    assert limiter.check("user-a")[0] is False

    # Key B has its own independent bucket
    assert limiter.check("user-b")[0] is True
    assert limiter.check("user-b")[0] is False

    # Reset Key A
    limiter.reset("user-a")
    assert limiter.check("user-a")[0] is True


def test_rate_limit_middleware_blocks_burst_and_returns_429() -> None:
    async def sample_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def health_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "healthy"})

    routes = [
        Route("/api/test", sample_endpoint),
        Route("/healthz", health_endpoint),
    ]

    app = Starlette(routes=routes)
    test_limiter = RateLimiter(requests_per_minute=60, burst=2)
    app.add_middleware(RateLimitMiddleware, limiter=test_limiter)

    client = TestClient(app)

    # First 2 requests succeed (burst capacity 2)
    r1 = client.get("/api/test")
    assert r1.status_code == 200

    r2 = client.get("/api/test")
    assert r2.status_code == 200

    # 3rd request exceeds limit -> 429
    r3 = client.get("/api/test")
    assert r3.status_code == 429
    assert "Retry-After" in r3.headers
    assert r3.json()["error"] == "rate_limit_exceeded"

    # Health check endpoint is exempt from rate limiting
    for _ in range(5):
        r_health = client.get("/healthz")
        assert r_health.status_code == 200


def test_rate_limit_middleware_respects_bearer_token() -> None:
    async def sample_endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/api/data", sample_endpoint)])
    test_limiter = RateLimiter(requests_per_minute=60, burst=1)
    app.add_middleware(RateLimitMiddleware, limiter=test_limiter)

    client = TestClient(app)

    # Token 1 consumes its allowance
    r1 = client.get("/api/data", headers={"Authorization": "Bearer token-11111111111111111111"})
    assert r1.status_code == 200
    r1_blocked = client.get("/api/data", headers={"Authorization": "Bearer token-11111111111111111111"})
    assert r1_blocked.status_code == 429

    # Token 2 has separate limit
    r2 = client.get("/api/data", headers={"Authorization": "Bearer token-22222222222222222222"})
    assert r2.status_code == 200
