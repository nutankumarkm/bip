"""Uploader sending batches from the SQLite outbox to BIP cloud with request signing."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bip.gateway.keys import sign_request
from bip.gateway.outbox import LocalOutbox


class OutboxUploader:
    """Reads pending punches from local outbox and uploads in batches with Ed25519 signing."""

    def __init__(
        self,
        outbox: LocalOutbox,
        cloud_url: str,
        gateway_id: str,
        private_key: Ed25519PrivateKey,
        batch_size: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.outbox = outbox
        self.cloud_url = cloud_url.rstrip("/")
        self.gateway_id = gateway_id
        self.private_key = private_key
        self.batch_size = min(max(batch_size, 1), 500)
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

    async def upload_pending(self, client: httpx.AsyncClient | None = None) -> int:
        """Upload one or more batches of pending punches. Returns count of uploaded punches."""
        http = client or self._external_client
        close_client = False
        if http is None:
            http = httpx.AsyncClient(timeout=30.0)
            close_client = True

        total_uploaded = 0
        try:
            # Peek up to batch_size items from outbox
            items = self.outbox.peek(limit=self.batch_size)
            if not items:
                return 0

            # Group punches or upload per item/batch
            for item in items:
                row_id = item["id"]
                serial = item["device_serial"]
                punches = item["punches"]
                batch_id = str(uuid.uuid4())

                payload_dict = {
                    "batch_id": batch_id,
                    "device_id": serial,
                    "events": punches,
                }
                body_bytes = json.dumps(payload_dict).encode("utf-8")
                path = "/gw/v1/punches:batch"
                headers = self._build_signed_headers("POST", path, body_bytes)
                url = f"{self.cloud_url}{path}"

                resp = await http.post(url, content=body_bytes, headers=headers)
                if resp.status_code in (200, 201):
                    self.outbox.mark_uploaded([row_id])
                    total_uploaded += len(punches)
                else:
                    # Non-successful status; stop processing to backoff
                    break

            return total_uploaded
        finally:
            if close_client and http:
                await http.aclose()

    async def run_loop(self, poll_interval: float = 5.0) -> None:
        """Continuously upload pending punches with exponential backoff on errors."""
        self._running = True
        backoff = 1.0
        max_backoff = 60.0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while self._running:
                try:
                    uploaded = await self.upload_pending(client=client)
                    if uploaded > 0:
                        backoff = 1.0  # Reset backoff on success
                        continue  # Keep uploading if there might be more
                    await asyncio.sleep(poll_interval)
                except Exception:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, max_backoff)

    def stop(self) -> None:
        self._running = False
