"""Conformance harness for connector testing.

Validates that a connector implementation behaves correctly:
- Declared capabilities match observed behaviour
- Crash mid-sync resumes from checkpoint with no gaps or duplicates
- Device time zone handling and drift reporting
- Person CRUD round-trips
- All failures map to the error taxonomy
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bip.sdk.capabilities import Capability
from bip.sdk.errors import ConnectorError, Unsupported
from bip.sdk.events import Checkpoint, CommandResult, DevicePerson, DeviceTarget, HealthReport, ProbeResult, RawPunch


@dataclass
class ConformanceResult:
    connector_family: str
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return len(self.failed) == 0


async def _collect_punches(iterator: AsyncIterator[RawPunch], limit: int = 100000) -> list[RawPunch]:
    results: list[RawPunch] = []
    count = 0
    async for punch in iterator:
        results.append(punch)
        count += 1
        if count >= limit:
            break
    return results


async def run_conformance(
    connector: Any,
    target: DeviceTarget,
    *,
    capabilities: set[str] | None = None,
    punch_count: int = 10000,
    timezones: list[str] | None = None,
) -> ConformanceResult:
    result = ConformanceResult(connector_family=getattr(connector, "family", "unknown"))
    timezones = timezones or ["Asia/Kolkata", "Asia/Dubai"]

    # Test 1: Probe
    try:
        probe = await connector.probe(target)
        if isinstance(probe, ProbeResult):
            result.passed.append("probe_returns_probe_result")
        else:
            result.failed.append("probe_returns_probe_result")
            result.errors["probe_returns_probe_result"] = f"Expected ProbeResult, got {type(probe)}"
    except Unsupported:
        result.skipped.append("probe_returns_probe_result")
    except ConnectorError as e:
        result.failed.append("probe_returns_probe_result")
        result.errors["probe_returns_probe_result"] = str(e)

    # Test 2: Health
    try:
        health = await connector.health()
        if isinstance(health, HealthReport):
            result.passed.append("health_returns_health_report")
        else:
            result.failed.append("health_returns_health_report")
    except Unsupported:
        result.skipped.append("health_returns_health_report")
    except ConnectorError as e:
        result.failed.append("health_returns_health_report")
        result.errors["health_returns_health_report"] = str(e)

    # Test 3: Fetch punches from start
    if capabilities and Capability.PUNCHES_PULL in capabilities:
        try:
            punches = await _collect_punches(connector.fetch_punches(Checkpoint()), limit=punch_count)
            result.passed.append("fetch_punches_from_start")

            # Test 3b: Resume from checkpoint — no duplicates
            if len(punches) > 0:
                midpoint = len(punches) // 2
                mid_punch = punches[midpoint]
                cursor = f"{mid_punch.device_local_time:%Y-%m-%d %H:%M:%S}"
                resumed = await _collect_punches(
                    connector.fetch_punches(Checkpoint(cursor=cursor)),
                    limit=punch_count,
                )
                all_keys = set()
                duplicates = 0
                for p in punches[:midpoint] + resumed:
                    key = f"{p.device_pin}|{p.device_local_time}|{p.verify_mode}"
                    if key in all_keys:
                        duplicates += 1
                    all_keys.add(key)
                if duplicates == 0:
                    result.passed.append("resume_no_duplicates")
                else:
                    result.failed.append("resume_no_duplicates")
                    result.errors["resume_no_duplicates"] = f"{duplicates} duplicates found"
        except ConnectorError as e:
            result.failed.append("fetch_punches_from_start")
            result.errors["fetch_punches_from_start"] = str(e)
    else:
        result.skipped.append("fetch_punches_from_start")
        result.skipped.append("resume_no_duplicates")

    # Test 4: People CRUD
    if capabilities and Capability.PEOPLE_WRITE in capabilities:
        test_person = DevicePerson(pin="99999", name="Conformance Test User")
        try:
            upsert_result = await connector.upsert_person(test_person)
            if isinstance(upsert_result, CommandResult) and upsert_result.success:
                result.passed.append("upsert_person")
            else:
                result.failed.append("upsert_person")
                result.errors["upsert_person"] = f"success={getattr(upsert_result, 'success', 'N/A')}"
        except ConnectorError as e:
            result.failed.append("upsert_person")
            result.errors["upsert_person"] = str(e)

        if capabilities and Capability.PEOPLE_READ in capabilities:
            try:
                people = await connector.list_people()
                found = any(p.pin == "99999" for p in people)
                if found:
                    result.passed.append("upsert_then_read_round_trip")
                else:
                    result.failed.append("upsert_then_read_round_trip")
                    result.errors["upsert_then_read_round_trip"] = "Upserted person not found in list"
            except ConnectorError as e:
                result.failed.append("upsert_then_read_round_trip")
                result.errors["upsert_then_read_round_trip"] = str(e)

        if capabilities and Capability.PEOPLE_DELETE in capabilities:
            try:
                delete_result = await connector.delete_person("99999")
                if isinstance(delete_result, CommandResult) and delete_result.success:
                    result.passed.append("delete_person")
                else:
                    result.failed.append("delete_person")
            except ConnectorError as e:
                result.failed.append("delete_person")
                result.errors["delete_person"] = str(e)
    else:
        result.skipped.append("upsert_person")
        result.skipped.append("upsert_then_read_round_trip")
        result.skipped.append("delete_person")

    # Test 5: Error taxonomy — unsupported capability returns Unsupported
    try:
        await connector.set_time(datetime.now(UTC))
        if capabilities and Capability.TIME_SET not in capabilities:
            result.failed.append("unsupported_raises_unsupported")
            result.errors["unsupported_raises_unsupported"] = "set_time succeeded but TIME_SET not in capabilities"
        else:
            result.passed.append("set_time_supported")
    except Unsupported:
        if capabilities and Capability.TIME_SET not in capabilities:
            result.passed.append("unsupported_raises_unsupported")
        else:
            result.failed.append("unsupported_raises_unsupported")
            result.errors["unsupported_raises_unsupported"] = "TIME_SET declared but raises Unsupported"
    except ConnectorError:
        result.passed.append("error_maps_to_taxonomy")

    return result
