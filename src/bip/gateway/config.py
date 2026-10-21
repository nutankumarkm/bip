"""Gateway agent configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class GatewayConfig(BaseSettings):
    model_config = {"env_prefix": "BIP_GW_"}

    gateway_id: str = ""
    cloud_url: str = "http://127.0.0.1:8080"
    data_dir: Path = Path("./gateway_data")
    poll_interval_seconds: int = 30
    heartbeat_interval_seconds: int = 60
    upload_batch_size: int = 100
    local_feed_port: int = 47800
    local_feed_host: str = "127.0.0.1"
    local_feed_token: str = ""
    discovery_subnet: str = "192.168.1.0/24"
    discovery_ports: list[int] = Field(default_factory=lambda: [4370, 80, 443])
    log_level: str = "INFO"
    private_key_path: Path | None = None
    update_public_key: str = ""
    version: str = "0.1.0"

    def get_key_path(self) -> Path:
        if self.private_key_path:
            return self.private_key_path
        return self.data_dir / "gateway_ed25519.key"

    def get_outbox_db_path(self) -> Path:
        return self.data_dir / "outbox.sqlite3"

    def get_local_token_path(self) -> Path:
        return self.data_dir / "local_token.txt"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(mode="json")
        # Ensure paths serialize to str
        data["data_dir"] = str(self.data_dir)
        if self.private_key_path:
            data["private_key_path"] = str(self.private_key_path)
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> GatewayConfig:
        if not path.exists():
            return cls()
        data: dict[str, Any] = json.loads(path.read_text())
        return cls(**data)
