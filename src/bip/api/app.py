"""BIP API application — consumer API, gateway API, and ops console."""

from __future__ import annotations

from fastapi import FastAPI

from bip.api.routes.oauth import router as oauth_router
from bip.api.routes.v1 import router as v1_router
from bip.core.logging import setup_logging
from bip.core.settings import settings

setup_logging(settings.log_level, settings.log_format)

app = FastAPI(
    title="BIP API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

app.include_router(oauth_router)
app.include_router(v1_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
