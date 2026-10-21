"""BIP API application — consumer API, gateway API, and ops console."""

from __future__ import annotations

from fastapi import FastAPI

from bip.core.logging import setup_logging
from bip.core.settings import settings

setup_logging(settings.log_level, settings.log_format)

app = FastAPI(
    title="BIP API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
