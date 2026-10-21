"""File import connector adapter conforming to SDK Connector protocol (ADR-002, section 8.7)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

from bip.connectors.file_import.importer import FileImporter
from bip.sdk.capabilities import Capability
from bip.sdk.errors import Unsupported
from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    RawPunch,
)


class FileImportConnector:
    """Connector that reads attendance records from export files (CSV, XLSX, DAT)."""

    family: str = "file_import"
    mode: Literal["file"] = "file"

    CAPABILITIES: ClassVar[set[Capability]] = {
        Capability.PUNCHES_PULL,
        Capability.DEVICE_INFO,
    }

    def __init__(self, file_path: Path | str | None = None, content: str | bytes | None = None, format: str = "csv") -> None:
        self.file_path = Path(file_path) if file_path else None
        self.content = content
        self.format = format.lower()
        self.importer = FileImporter()

    def _get_raw_data(self) -> bytes:
        if self.content is not None:
            return self.content.encode() if isinstance(self.content, str) else self.content
        if self.file_path and self.file_path.exists():
            return self.file_path.read_bytes()
        return b""

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        data = self._get_raw_data()
        return ProbeResult(
            serial=target.serial or "FILE-IMPORT",
            model=f"File Import ({self.format.upper()})",
            capabilities=[c.value for c in self.CAPABILITIES],
            extra={"bytes": len(data), "format": self.format},
        )

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        data = self._get_raw_data()
        if not data:
            return

        if self.format == "csv":
            report = self.importer.parse_csv(data)
        elif self.format == "xlsx":
            report = self.importer.parse_xlsx(data)
        elif self.format in ("dat", "attlog.dat"):
            report = self.importer.parse_dat(data)
        else:
            report = self.importer.parse_csv(data)

        cursor_dt = None
        if since.cursor:
            with contextlib.suppress(ValueError):
                cursor_dt = datetime.fromisoformat(since.cursor)

        for p in report.punches:
            if cursor_dt and p.device_local_time <= cursor_dt:
                continue
            yield p

    async def list_people(self) -> list[DevicePerson]:
        raise Unsupported("File import connector does not support listing people")

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        raise Unsupported("File import connector is read-only; cannot upsert people")

    async def delete_person(self, pin: str) -> CommandResult:
        raise Unsupported("File import connector is read-only; cannot delete people")

    async def set_time(self, now: datetime) -> CommandResult:
        raise Unsupported("File import connector cannot set device time")

    async def health(self) -> HealthReport:
        has_file = (self.file_path and self.file_path.exists()) or (self.content is not None)
        return HealthReport(reachable=bool(has_file), serial="FILE-IMPORT")
