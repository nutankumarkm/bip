"""Gateway command runner for executing commands dispatched from cloud."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bip.gateway.keys import sign_request
from bip.sdk.events import DevicePerson


class CommandRunner:
    """Long-polls for pending commands, dispatches them to connectors, and posts results."""

    def __init__(
        self,
        cloud_url: str,
        gateway_id: str,
        private_key: Ed25519PrivateKey,
        connectors: dict[str, Any],  # device_id/serial -> connector
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self.gateway_id = gateway_id
        self.private_key = private_key
        self.connectors = connectors
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

    async def poll_and_execute(self, client: httpx.AsyncClient | None = None, wait: int = 30) -> int:
        """Poll once for queued commands and execute them. Returns number of commands executed."""
        http = client or self._external_client
        close_client = False
        if http is None:
            http = httpx.AsyncClient(timeout=float(wait + 10))
            close_client = True

        try:
            path_with_query = f"/gw/v1/commands?wait={wait}"
            headers = self._build_signed_headers("GET", path_with_query, b"")
            url = f"{self.cloud_url}{path_with_query}"

            resp = await http.get(url, headers=headers)
            if resp.status_code != 200:
                return 0

            data = resp.json()
            commands = data.get("commands", [])
            executed = 0

            for cmd in commands:
                cmd_id = cmd["id"]
                cmd_type = cmd.get("type", "")
                params = cmd.get("params", {})
                device_id = cmd.get("device_id", "")
                serial = cmd.get("serial", device_id)

                connector = self.connectors.get(device_id) or self.connectors.get(serial)
                success = False
                message = ""
                result_data: dict[str, Any] = {}

                if not connector:
                    message = f"No connector registered for device {device_id}"
                else:
                    try:
                        if cmd_type in ("set_user", "DATA UPDATE USERINFO"):
                            person = DevicePerson(
                                pin=str(params.get("pin", "")),
                                name=str(params.get("name", "")),
                                card_no=str(params.get("card", "")) if params.get("card") else None,
                            )
                            res = await connector.upsert_person(person)
                            success = res.success
                            message = res.message
                        elif cmd_type in ("delete_user", "DATA DELETE USERINFO"):
                            pin = str(params.get("pin", ""))
                            res = await connector.delete_person(pin)
                            success = res.success
                            message = res.message
                        elif cmd_type in ("set_time", "TIME_SET"):
                            now = datetime.now(UTC)
                            res = await connector.set_time(now)
                            success = res.success
                            message = res.message
                        else:
                            success = True
                            message = f"Command {cmd_type} executed (acknowledged)"
                    except Exception as e:
                        success = False
                        message = str(e)

                # Post command result back to cloud
                result_path = f"/gw/v1/commands/{cmd_id}/result"
                result_body = json.dumps(
                    {
                        "command_id": cmd_id,
                        "success": success,
                        "return_code": 0 if success else 1,
                        "message": message,
                        "result": result_data,
                    }
                ).encode("utf-8")
                result_headers = self._build_signed_headers("POST", result_path, result_body)
                await http.post(
                    f"{self.cloud_url}{result_path}",
                    content=result_body,
                    headers=result_headers,
                )
                executed += 1

            return executed
        finally:
            if close_client and http:
                await http.aclose()

    async def run_loop(self) -> None:
        """Run the command polling loop."""
        self._running = True
        async with httpx.AsyncClient(timeout=45.0) as client:
            while self._running:
                try:
                    await self.poll_and_execute(client=client, wait=30)
                except Exception:
                    await asyncio.sleep(5.0)

    def stop(self) -> None:
        self._running = False
