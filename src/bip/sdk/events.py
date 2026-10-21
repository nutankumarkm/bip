"""Punch event model and related types."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

VerifyMode = Literal["fingerprint", "face", "card", "pin", "palm", "other"]
Source = Literal["adms", "zk_tcp", "isapi", "biotime", "cosec", "db_read", "file"]
PersonType = Literal["student", "staff", "employee"]


class PunchEvent(BaseModel):
    id: str | None = None
    org_id: str
    site_id: str
    device_id: str
    person_id: str | None = None
    device_pin: str
    device_local_time: datetime
    device_tz: str = "Asia/Kolkata"
    occurred_at: datetime
    corrected_at: datetime | None = None
    verify_mode: VerifyMode
    io_state: str | None = None
    work_code: str | None = None
    source: Source
    dedupe_key: str = ""
    raw: dict[str, Any] | None = None
    received_at: datetime | None = None

    def compute_dedupe_key(self, device_identity: str) -> str:
        payload = f"{device_identity}|{self.device_pin}|{self.device_local_time:%Y-%m-%d %H:%M:%S}|{self.verify_mode}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def with_dedupe(self, device_identity: str) -> PunchEvent:
        return self.model_copy(update={"dedupe_key": self.compute_dedupe_key(device_identity)})


class RawPunch(BaseModel):
    device_pin: str
    device_local_time: datetime
    verify_mode: VerifyMode = "other"
    io_state: str | None = None
    work_code: str | None = None
    raw: dict[str, Any] | None = None


class DevicePerson(BaseModel):
    pin: str
    name: str = ""
    card_no: str | None = None
    group: int = 1
    privilege: int = 0
    fingerprints: int = 0
    face: bool = False
    palm: bool = False
    card: bool = False


class CommandResult(BaseModel):
    cmd_no: int | None = None
    success: bool
    return_code: int = 0
    message: str = ""


class ProbeResult(BaseModel):
    serial: str | None = None
    model: str | None = None
    firmware: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    reachable: bool
    serial: str | None = None
    time: datetime | None = None
    drift_seconds: int | None = None
    log_fill_pct: int | None = None
    firmware: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class DeviceTarget(BaseModel):
    address: str
    port: int = 4370
    password: int = 0
    serial: str | None = None


class Checkpoint(BaseModel):
    cursor: str = ""
    kind: str = "punches"
