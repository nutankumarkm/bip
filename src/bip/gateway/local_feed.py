"""Gateway local feed API (section 11).

Serves punches directly to LearnX on localhost when cloud connectivity is unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from bip.gateway.outbox import LocalOutbox


class PunchFeedResponse(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None = None


def create_local_feed_app(outbox: LocalOutbox, token_path: Path | None = None, static_token: str = "") -> FastAPI:
    """Create a FastAPI application for the gateway local feed."""
    app = FastAPI(title="BIP Gateway Local Feed", docs_url=None, redoc_url=None)

    def _get_expected_token() -> str:
        if static_token:
            return static_token
        if token_path and token_path.exists():
            return token_path.read_text().strip()
        return ""

    def verify_token(authorization: str = Header(None)) -> bool:
        expected = _get_expected_token()
        if not expected:
            return True  # If no token configured, allow local access

        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

        token = authorization
        if authorization.startswith("Bearer "):
            token = authorization[7:].strip()

        if token != expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid local feed token")
        return True

    @app.get("/v1/punches", response_model=PunchFeedResponse)
    async def get_punches(
        cursor: str | None = None,
        limit: int = 100,
        _: bool = Depends(verify_token),
    ) -> PunchFeedResponse:
        after_id = 0
        if cursor and cursor.isdigit():
            after_id = int(cursor)

        items, last_id = outbox.get_punches_feed(after_id=after_id, limit=limit)
        next_cursor = str(last_id) if items and len(items) >= limit else None

        return PunchFeedResponse(items=items, next_cursor=next_cursor)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "gateway_local_feed"}

    return app
