"""Matrix COSEC connector stub (ADR-002, section 8.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel

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


class CosecConfig(BaseModel):
    base_url: str = "http://localhost:8080"
    username: str = ""
    password: str = ""


class MatrixCosecConnector:
    """Stub connector for Matrix COSEC systems.

    Matrix COSEC web APIs require official Matrix documentation and depends on the customer's licence.
    Declares no capabilities.
    """

    family: str = "cosec"
    mode: Literal["vendor"] = "vendor"

    CAPABILITIES: ClassVar[set[Capability]] = set()

    def __init__(self, config: CosecConfig | None = None) -> None:
        self.config = config or CosecConfig()

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        return ProbeResult(
            serial=target.serial or "COSEC-STUB",
            model="Matrix COSEC (Stub)",
            capabilities=[],
            extra={"note": "Matrix COSEC requires customer license and vendor API docs"},
        )

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        raise Unsupported("Matrix COSEC connector is a stub and cannot pull punches")
        if False:
            yield

    async def list_people(self) -> list[DevicePerson]:
        raise Unsupported("Matrix COSEC connector is a stub and cannot list people")

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        raise Unsupported("Matrix COSEC connector is a stub and cannot upsert people")

    async def delete_person(self, pin: str) -> CommandResult:
        raise Unsupported("Matrix COSEC connector is a stub and cannot delete people")

    async def set_time(self, now: datetime) -> CommandResult:
        raise Unsupported("Matrix COSEC connector is a stub and cannot set time")

    async def health(self) -> HealthReport:
        return HealthReport(
            reachable=False,
            serial="COSEC-STUB",
            extra={"status": "stub_only", "message": "Matrix COSEC requires documentation and license"},
        )
