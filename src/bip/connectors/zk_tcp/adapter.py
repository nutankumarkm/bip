"""ZK TCP binary protocol connector adapter (ADR-002, section 8.2).

Isolates pyzk into a single adapter implementing the BIP Connector protocol.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from bip.sdk.capabilities import Capability
from bip.sdk.errors import ProtocolError, Unreachable
from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    RawPunch,
    VerifyMode,
)


def _get_default_zk_factory() -> Any:
    try:
        from zk import ZK  # type: ignore[import-untyped]

        return ZK
    except ImportError:
        from bip.emulators.fake_zk import FakeZKClient

        return FakeZKClient


class ZKConnector:
    """Adapter for ZKTeco devices using the binary TCP protocol (TCP 4370)."""

    family: str = "zk_tcp"
    mode: Literal["pull"] = "pull"

    CAPABILITIES: ClassVar[set[Capability]] = {
        Capability.PUNCHES_PULL,
        Capability.PEOPLE_READ,
        Capability.PEOPLE_WRITE,
        Capability.PEOPLE_DELETE,
        Capability.TIME_SET,
        Capability.DEVICE_INFO,
    }

    def __init__(
        self,
        target: DeviceTarget | None = None,
        *,
        client_factory: Any = None,
    ) -> None:
        self.target = target or DeviceTarget(address="127.0.0.1", port=4370)
        self.client_factory = client_factory or _get_default_zk_factory()

    def _create_client(self, target: DeviceTarget | None = None) -> Any:
        t = target or self.target
        return self.client_factory(
            ip=t.address,
            port=t.port,
            timeout=5,
            password=t.password,
            force_udp=False,
            ommit_ping=False,
        )

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        """Probe a target device to discover serial and firmware."""

        def _do_probe() -> ProbeResult:
            client = self._create_client(target)
            try:
                client.connect()
                serial = client.get_serialnumber()
                firmware = client.get_firmware_version()
                client.disconnect()
                return ProbeResult(
                    serial=serial,
                    model="ZKTeco Standalone (TCP)",
                    firmware=firmware,
                    capabilities=[c.value for c in self.CAPABILITIES],
                    extra={"address": target.address, "port": target.port},
                )
            except Exception as e:
                raise Unreachable(f"Failed to probe ZK device at {target.address}:{target.port}: {e}") from e

        return await asyncio.to_thread(_do_probe)

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        """Fetch attendance punches newer than checkpoint cursor."""

        def _get_records() -> list[Any]:
            client = self._create_client()
            try:
                client.connect()
                client.disable_device()
                try:
                    records = client.get_attendance()
                finally:
                    client.enable_device()
                    client.disconnect()
                return records
            except Exception as e:
                raise ProtocolError(f"Error fetching attendance records: {e}") from e

        records = await asyncio.to_thread(_get_records)

        # Parse cursor: could be an ISO string or a timestamp string
        cursor_dt = None
        if since.cursor:
            cursor_str = since.cursor.split("|")[0].strip()
            with contextlib.suppress(ValueError):
                cursor_dt = datetime.fromisoformat(cursor_str)
            if cursor_dt is None:
                with contextlib.suppress(ValueError):
                    cursor_dt = datetime.strptime(cursor_str, "%Y-%m-%d %H:%M:%S")

        # Sort records by timestamp
        def get_ts(r: Any) -> datetime:
            return getattr(r, "timestamp", datetime.min)

        sorted_records = sorted(records, key=get_ts)

        for rec in sorted_records:
            rec_dt = rec.timestamp
            # If naive, treat as UTC or local time
            if cursor_dt:
                rec_cmp = rec_dt.replace(tzinfo=None)
                cur_cmp = cursor_dt.replace(tzinfo=None)
                if rec_cmp <= cur_cmp:
                    continue

            # Map status / punch to verify mode
            status = getattr(rec, "status", 0)
            verify_mode: VerifyMode = "fingerprint"
            if status == 1:
                verify_mode = "card"
            elif status == 2:
                verify_mode = "pin"
            elif status == 3:
                verify_mode = "face"
            elif status == 4:
                verify_mode = "palm"

            yield RawPunch(
                device_pin=str(rec.user_id),
                device_local_time=rec_dt,
                verify_mode=verify_mode,
                work_code=str(getattr(rec, "punch", 0)),
                raw={"status": status, "punch": getattr(rec, "punch", 0)},
            )

    async def list_people(self) -> list[DevicePerson]:
        """List all users enrolled on the device."""

        def _do_list() -> list[DevicePerson]:
            client = self._create_client()
            try:
                client.connect()
                users = client.get_users()
                client.disconnect()
                return [
                    DevicePerson(
                        pin=str(u.user_id),
                        name=getattr(u, "name", ""),
                        card_no=str(getattr(u, "card", 0)) if getattr(u, "card", 0) else None,
                        group=int(getattr(u, "group_id", 1) or 1),
                        privilege=int(getattr(u, "privilege", 0)),
                    )
                    for u in users
                ]
            except Exception as e:
                raise ProtocolError(f"Error listing users: {e}") from e

        return await asyncio.to_thread(_do_list)

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        """Add or update a user on the device."""

        def _do_upsert() -> CommandResult:
            client = self._create_client()
            try:
                client.connect()
                card_num = int(person.card_no) if person.card_no and person.card_no.isdigit() else 0
                pin_int = int(person.pin) if person.pin.isdigit() else 0
                client.set_user(
                    uid=pin_int,
                    name=person.name,
                    privilege=person.privilege,
                    group_id=str(person.group),
                    user_id=person.pin,
                    card=card_num,
                )
                client.disconnect()
                return CommandResult(success=True, message=f"Upserted user {person.pin}")
            except Exception as e:
                raise ProtocolError(f"Failed to upsert person {person.pin}: {e}") from e

        return await asyncio.to_thread(_do_upsert)

    async def delete_person(self, pin: str) -> CommandResult:
        """Delete a user from the device."""

        def _do_delete() -> CommandResult:
            client = self._create_client()
            try:
                client.connect()
                pin_int = int(pin) if pin.isdigit() else 0
                client.delete_user(uid=pin_int, user_id=pin)
                client.disconnect()
                return CommandResult(success=True, message=f"Deleted user {pin}")
            except Exception as e:
                raise ProtocolError(f"Failed to delete person {pin}: {e}") from e

        return await asyncio.to_thread(_do_delete)

    async def set_time(self, now: datetime) -> CommandResult:
        """Synchronize the device clock."""

        def _do_set_time() -> CommandResult:
            client = self._create_client()
            try:
                client.connect()
                client.set_time(now)
                client.disconnect()
                return CommandResult(success=True, message=f"Set device time to {now.isoformat()}")
            except Exception as e:
                raise ProtocolError(f"Failed to set device time: {e}") from e

        return await asyncio.to_thread(_do_set_time)

    async def health(self) -> HealthReport:
        """Check device reachability, clock drift, and memory capacity."""

        def _do_health() -> HealthReport:
            client = self._create_client()
            try:
                client.connect()
                dev_time = client.get_time()
                serial = client.get_serialnumber()
                firmware = client.get_firmware_version()
                sizes = client.read_sizes()
                client.disconnect()

                now = datetime.now(UTC)
                drift_s = int(abs((now.replace(tzinfo=None) - dev_time.replace(tzinfo=None)).total_seconds()))
                attlog = sizes.get("attlog", 0)
                attlog_cap = sizes.get("attlog_cap", 100000) or 100000
                log_fill_pct = int((attlog / attlog_cap) * 100)

                return HealthReport(
                    reachable=True,
                    serial=serial,
                    time=dev_time,
                    drift_seconds=drift_s,
                    log_fill_pct=log_fill_pct,
                    firmware=firmware,
                    extra=sizes,
                )
            except Exception as e:
                return HealthReport(
                    reachable=False,
                    extra={"error": str(e)},
                )

        return await asyncio.to_thread(_do_health)
