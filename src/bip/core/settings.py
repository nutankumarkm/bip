"""Application settings loaded from environment variables."""

from __future__ import annotations

import base64
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "BIP_", "env_file": ".env", "extra": "ignore"}

    database_url: str = "postgresql+asyncpg://bip_owner:changeme@localhost:5432/bip"
    database_url_sync: str = "postgresql://bip_owner:changeme@localhost:5432/bip"

    master_key: str = "dGVzdC1rZXktMzItYnl0ZXMtZm9yLWRldg=="
    jwt_secret: str = "dev-jwt-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 15

    edge_host: str = "0.0.0.0"
    edge_port: int = 8081
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    gateway_clock_skew_max_seconds: int = 300
    worker_batch_size: int = 100
    webhook_timeout_seconds: int = 10

    @property
    def master_key_bytes(self) -> bytes:
        return base64.b64decode(self.master_key)


settings = Settings()
