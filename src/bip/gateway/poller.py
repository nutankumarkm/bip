"""Poller for pulling punches from LAN devices into local outbox."""

from __future__ import annotations

import asyncio
from typing import Any

from bip.gateway.outbox import LocalOutbox
from bip.sdk.events import Checkpoint, RawPunch


class DevicePoller:
    """Polls pull-based biometric devices and enqueues punches into the local outbox."""

    def __init__(self, outbox: LocalOutbox) -> None:
        self.outbox = outbox
        self._connectors: dict[str, Any] = {}  # serial -> connector instance
        self._running = False

    def register_device(self, serial: str, connector: Any) -> None:
        self._connectors[serial] = connector

    def unregister_device(self, serial: str) -> None:
        self._connectors.pop(serial, None)

    async def poll_device(self, serial: str) -> int:
        """Poll a single device and return count of new punches enqueued."""
        connector = self._connectors.get(serial)
        if not connector:
            return 0

        cursor = self.outbox.get_checkpoint(serial)
        checkpoint = Checkpoint(cursor=cursor)

        new_punches: list[dict[str, Any]] = []
        last_cursor = cursor

        try:
            async for punch in connector.fetch_punches(checkpoint):
                data = punch.model_dump(mode="json") if isinstance(punch, RawPunch) else dict(punch)
                new_punches.append(data)
                # Track latest punch timestamp
                ts = data.get("device_local_time")
                if ts:
                    last_cursor = str(ts)
        except Exception:
            # Device may be unreachable or busy; log and continue
            return 0

        if new_punches:
            self.outbox.enqueue(serial, new_punches)
            if last_cursor:
                self.outbox.save_checkpoint(serial, last_cursor)

        return len(new_punches)

    async def poll_all(self) -> dict[str, int]:
        """Poll all registered devices."""
        results = {}
        for serial in list(self._connectors.keys()):
            results[serial] = await self.poll_device(serial)
        return results

    async def run_loop(self, interval_seconds: int = 30) -> None:
        """Run the polling loop indefinitely until stopped."""
        self._running = True
        while self._running:
            await self.poll_all()
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False
