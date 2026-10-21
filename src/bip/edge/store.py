"""Edge storage abstraction — in-memory for testing, Postgres for production."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class EdgeStore:
    """In-memory Edge store for testing. Production replaces with async Postgres."""

    def __init__(self) -> None:
        self._devices: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, dict[str, Any]] = {}
        self._raw_uploads: list[dict[str, Any]] = []
        self._checkpoints: dict[str, dict[str, str]] = {}
        self._commands: dict[str | None, list[tuple[int, str]]] = {}
        self._command_states: dict[int, str] = {}

    async def register_device(self, serial: str, device: dict[str, Any]) -> None:
        self._devices[serial] = device

    async def lookup_device(self, serial: str) -> dict[str, Any] | None:
        return self._devices.get(serial)

    async def upsert_pending(self, serial: str, ip: str, info: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        if serial in self._pending:
            self._pending[serial]["last_seen_at"] = now
            self._pending[serial]["last_ip"] = ip
            self._pending[serial]["info"] = info
        else:
            self._pending[serial] = {
                "serial": serial,
                "vendor": "zk",
                "first_seen_at": now,
                "last_seen_at": now,
                "last_ip": ip,
                "info": info,
            }

    async def get_pending_devices(self) -> list[dict[str, Any]]:
        return list(self._pending.values())

    async def save_raw_upload(
        self,
        device_id: str | None,
        serial: str,
        family: str,
        endpoint: str,
        query: dict[str, Any],
        body: str,
    ) -> int:
        upload_id = len(self._raw_uploads) + 1
        self._raw_uploads.append(
            {
                "id": upload_id,
                "device_id": device_id,
                "serial": serial,
                "family": family,
                "endpoint": endpoint,
                "query": query,
                "body": body,
                "received_at": datetime.now(UTC).isoformat(),
                "processed_at": None,
                "error": None,
            }
        )
        return upload_id

    async def get_unprocessed_uploads(self, limit: int = 100) -> list[dict[str, Any]]:
        return [u for u in self._raw_uploads if u["processed_at"] is None][:limit]

    async def mark_processed(self, upload_id: int, error: str | None = None) -> None:
        for u in self._raw_uploads:
            if u["id"] == upload_id:
                u["processed_at"] = datetime.now(UTC).isoformat()
                u["error"] = error
                break

    async def get_checkpoint(self, serial: str, kind: str) -> str | None:
        return self._checkpoints.get(serial, {}).get(kind)

    async def set_checkpoint(self, serial: str, kind: str, cursor: str) -> None:
        if serial not in self._checkpoints:
            self._checkpoints[serial] = {}
        self._checkpoints[serial][kind] = cursor

    async def queue_command(self, device_id: str | None, cmd_no: int, cmd_text: str) -> None:
        if device_id not in self._commands:
            self._commands[device_id] = []
        self._commands[device_id].append((cmd_no, cmd_text))
        self._command_states[cmd_no] = "queued"

    async def get_pending_commands(self, device_id: str | None) -> list[tuple[int, str]]:
        cmds = self._commands.get(device_id, [])
        return [(no, txt) for no, txt in cmds if self._command_states.get(no) == "queued"]

    async def mark_command_sent(self, cmd_no: int) -> None:
        self._command_states[cmd_no] = "sent"

    async def complete_command(self, cmd_no: int, success: bool, return_code: int) -> None:
        self._command_states[cmd_no] = "succeeded" if success else "failed"

    def get_raw_upload_count(self) -> int:
        return len(self._raw_uploads)

    def get_processed_count(self) -> int:
        return sum(1 for u in self._raw_uploads if u["processed_at"] is not None)
