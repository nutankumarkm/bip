"""Connector protocol definitions — pull-style and push-style."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    RawPunch,
)


class DeviceCommand:
    """Command to be sent to a device."""

    def __init__(self, cmd_no: int, type: str, params: dict | None = None) -> None:
        self.cmd_no = cmd_no
        self.type = type
        self.params = params or {}


class ParsedUpload:
    """Result of parsing a push upload."""

    def __init__(
        self,
        punches: list[RawPunch] | None = None,
        users: list[DevicePerson] | None = None,
        enrolment_counts: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.punches = punches or []
        self.users = users or []
        self.enrolment_counts = enrolment_counts or {}


@runtime_checkable
class Connector(Protocol):
    """Pull-style connector: gateway, vendor, and file connectors."""

    family: str
    mode: Literal["pull", "vendor", "file"]

    async def probe(self, target: DeviceTarget) -> ProbeResult: ...

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]: ...

    async def list_people(self) -> list[DevicePerson]: ...

    async def upsert_person(self, person: DevicePerson) -> CommandResult: ...

    async def delete_person(self, pin: str) -> CommandResult: ...

    async def set_time(self, now: datetime) -> CommandResult: ...

    async def health(self) -> HealthReport: ...


@runtime_checkable
class PushConnector(Protocol):
    """Push-style connector: device-initiated (ADMS/iClock)."""

    family: str

    def parse_upload(self, table: str, body: str) -> ParsedUpload: ...

    def render_commands(self, commands: list[DeviceCommand]) -> str: ...

    def parse_results(self, body: str) -> list[CommandResult]: ...
