"""BIP Device Edge — ADMS/iClock push endpoints."""

from __future__ import annotations

from fastapi import FastAPI

from bip.core.logging import setup_logging
from bip.core.settings import settings
from bip.edge.adms import router as adms_router

setup_logging(settings.log_level, settings.log_format)

app = FastAPI(
    title="BIP Device Edge",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)

app.include_router(adms_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "edge"}
