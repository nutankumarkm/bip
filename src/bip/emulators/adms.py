"""ADMS device emulator — simulates N devices pushing punches to the Edge."""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from bip.core.logging import get_logger, setup_logging

log = get_logger("bip.emulators.adms")


class EmulatedDevice:
    def __init__(
        self,
        serial: str,
        server_url: str,
        *,
        users: list[dict[str, str]] | None = None,
        log_capacity: int = 100000,
        clock_offset_s: int = 0,
        flaky_rate: float = 0.0,
        punches_per_interval: int = 5,
    ) -> None:
        self.serial = serial
        self.server_url = server_url.rstrip("/")
        self.users = users or [{"pin": str(10001 + i), "name": f"User {i}"} for i in range(20)]
        self.log_capacity = log_capacity
        self.clock_offset = timedelta(seconds=clock_offset_s)
        self.flaky_rate = flaky_rate
        self.punches_per_interval = punches_per_interval
        self.delay = 10
        self.stamp = "None"
        self.running = False
        self._punch_log: list[dict[str, Any]] = []
        self._sent_count = 0

    @property
    def device_time(self) -> datetime:
        return datetime.now(UTC) + self.clock_offset

    def generate_punches(self, count: int) -> list[dict[str, str]]:
        punches = []
        for _ in range(count):
            user = random.choice(self.users)
            ts = self.device_time.strftime("%Y-%m-%d %H:%M:%S")
            verify = random.choice(["1", "9", "4"])
            status = random.choice(["0", "1"])
            workcode = ""
            punch = {"pin": user["pin"], "ts": ts, "status": status, "verify": verify, "workcode": workcode}
            punches.append(punch)
            self._punch_log.append(punch)
        return punches

    def format_attlog(self, punches: list[dict[str, str]]) -> str:
        lines = []
        for p in punches:
            lines.append(f"{p['pin']}\t{p['ts']}\t{p['status']}\t{p['verify']}\t{p['workcode']}\t0\t0")
        return "\n".join(lines)

    async def handshake(self, client: httpx.AsyncClient) -> bool:
        try:
            resp = await client.get(
                f"{self.server_url}/iclock/cdata",
                params={"SN": self.serial, "options": "all"},
            )
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.startswith("Delay="):
                        self.delay = int(line.split("=", 1)[1])
                    elif line.startswith("ATTLOGStamp="):
                        self.stamp = line.split("=", 1)[1]
                return True
            return False
        except httpx.HTTPError:
            return False

    async def push_punches(self, client: httpx.AsyncClient, punches: list[dict[str, str]]) -> bool:
        if random.random() < self.flaky_rate:
            return False
        body = self.format_attlog(punches)
        stamp = self.device_time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            resp = await client.post(
                f"{self.server_url}/iclock/cdata",
                params={"SN": self.serial, "table": "ATTLOG", "Stamp": stamp},
                content=body,
                headers={"Content-Type": "text/plain"},
            )
            if resp.status_code == 200 and resp.text.startswith("OK"):
                self._sent_count += len(punches)
                return True
            return False
        except httpx.HTTPError:
            return False

    async def poll_commands(self, client: httpx.AsyncClient) -> str:
        try:
            resp = await client.get(
                f"{self.server_url}/iclock/getrequest",
                params={"SN": self.serial},
            )
            return resp.text if resp.status_code == 200 else ""
        except httpx.HTTPError:
            return ""

    async def run(self, duration_s: int = 0, punch_count: int = 0) -> int:
        self.running = True
        sent_total = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            ok = await self.handshake(client)
            if not ok:
                log.warning("handshake_failed", serial=self.serial)

            if punch_count > 0:
                remaining = punch_count
                while remaining > 0 and self.running:
                    batch = min(self.punches_per_interval, remaining)
                    punches = self.generate_punches(batch)
                    if await self.push_punches(client, punches):
                        sent_total += batch
                    remaining -= batch
                    await self.poll_commands(client)
                    await asyncio.sleep(0.1)
            elif duration_s > 0:
                end = asyncio.get_event_loop().time() + duration_s
                while asyncio.get_event_loop().time() < end and self.running:
                    punches = self.generate_punches(self.punches_per_interval)
                    if await self.push_punches(client, punches):
                        sent_total += len(punches)
                    await self.poll_commands(client)
                    await asyncio.sleep(max(0.1, self.delay))
            else:
                while self.running:
                    punches = self.generate_punches(self.punches_per_interval)
                    if await self.push_punches(client, punches):
                        sent_total += len(punches)
                    await self.poll_commands(client)
                    await asyncio.sleep(max(0.1, self.delay))

        return sent_total

    def stop(self) -> None:
        self.running = False


async def run_emulator(server_url: str, device_count: int, duration_s: int = 60) -> dict[str, int]:
    devices = [
        EmulatedDevice(
            serial=f"EMU{i:04d}",
            server_url=server_url,
            punches_per_interval=10,
        )
        for i in range(device_count)
    ]

    tasks = [asyncio.create_task(d.run(duration_s=duration_s)) for d in devices]
    results = await asyncio.gather(*tasks)

    total = sum(results)
    log.info("emulator_done", devices=device_count, total_punches=total)
    return {"devices": device_count, "total_punches": total}


def main() -> None:
    parser = argparse.ArgumentParser(description="ADMS Device Emulator")
    parser.add_argument("--devices", type=int, default=5)
    parser.add_argument("--server", type=str, default="http://localhost:8081")
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()

    setup_logging("INFO", "console")
    asyncio.run(run_emulator(args.server, args.devices, args.duration))


if __name__ == "__main__":
    main()
