"""Gateway heartbeat sender (ADR-009, section 10, section 11)."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bip.gateway.keys import sign_request
from bip.gateway.outbox import LocalOutbox
from bip.sdk.events import HealthReport


class HeartbeatSender:
    """Sends periodic heartbeats to cloud including queue depth, disk space, and device status."""

    def __init__(
        self,
        cloud_url: str,
        gateway_id: str,
        private_key: Ed25519PrivateKey,
        outbox: LocalOutbox,
        connectors: dict[str, Any],  # device_id -> connector
        version: str = "0.1.0",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self.gateway_id = gateway_id
        self.private_key = private_key
        self.outbox = outbox
        self.connectors = connectors
        self.version = version
        self._external_client = client
        self._running = False

    def _build_signed_headers(self, method: str, path_with_query: str, body: bytes) -> dict[str, str]:
        now_ts = int(time.time())
        sig = sign_request(self.private_key, method, path_with_query, body, now_ts)
        return {
            "Content-Type": "application/json",
            "X-BIP-Gateway": self.gateway_id,
            "X-BIP-Timestamp": str(now_ts),
            "X-BIP-Signature": sig,
        }

    async def send_heartbeat(self, client: httpx.AsyncClient | None = None) -> bool:
        """Collect metrics and send a single heartbeat to cloud."""
        http = client or self._external_client
        close_client = False
        if http is None:
            http = httpx.AsyncClient(timeout=10.0)
            close_client = True

        try:
            # Check disk free MB
            disk_free_mb = 1000.0
            try:
                disk = shutil.disk_usage(".")
                disk_free_mb = round(disk.free / (1024 * 1024), 1)
            except Exception:
                pass

            # Gather device health
            devices_status: list[dict[str, Any]] = []
            for dev_id, conn in self.connectors.items():
                reachable = False
                drift_s = 0
                log_fill = 0
                try:
                    health: HealthReport = await conn.health()
                    reachable = health.reachable
                    drift_s = health.drift_seconds or 0
                    log_fill = health.log_fill_pct or 0
                except Exception:
                    pass
                devices_status.append(
                    {
                        "device_id": dev_id,
                        "reachable": reachable,
                        "drift_s": drift_s,
                        "log_fill_pct": log_fill,
                    }
                )

            body_dict = {
                "version": self.version,
                "queue_depth": self.outbox.pending_count(),
                "disk_free_mb": disk_free_mb,
                "devices": devices_status,
            }
            body_bytes = json.dumps(body_dict).encode("utf-8")
            path = "/gw/v1/heartbeat"
            headers = self._build_signed_headers("POST", path, body_bytes)

            resp = await http.post(f"{self.cloud_url}{path}", content=body_bytes, headers=headers)
            return resp.status_code == 200
        except Exception:
            return False
        finally:
            if close_client and http:
                await http.aclose()

    async def run_loop(self, interval_seconds: int = 60) -> None:
        """Run the heartbeat loop."""
        self._running = True
        while self._running:
            await self.send_heartbeat()
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False
