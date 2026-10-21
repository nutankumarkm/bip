"""Tests for eTimeTrackLite read-only database connector adapter and conformance (ADR-002, section 8.6, M7)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bip.connectors.db_read.adapter import DbReadConfig, ETimeTrackLiteConnector
from bip.sdk.conformance import run_conformance
from bip.sdk.errors import Unsupported
from bip.sdk.events import Checkpoint, DevicePerson, DeviceTarget


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test_etimetracklite.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """CREATE TABLE DeviceLogs (
            UserId TEXT NOT NULL,
            LogDate TEXT NOT NULL,
            DeviceId TEXT NOT NULL
        )"""
    )
    base = datetime.now(UTC) - timedelta(hours=5)
    for i in range(20):
        t_str = (base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO DeviceLogs (UserId, LogDate, DeviceId) VALUES (?, ?, ?)",
            (f"EMP{100 + i}", t_str, "DEV-01"),
        )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def db_connector(test_db_path: Path) -> ETimeTrackLiteConnector:
    cfg = DbReadConfig(
        sqlite_path=str(test_db_path),
        table_name="DeviceLogs",
        column_user_id="UserId",
        column_log_date="LogDate",
        column_device_id="DeviceId",
    )
    return ETimeTrackLiteConnector(cfg)


@pytest.mark.asyncio
async def test_db_read_probe_and_health(db_connector: ETimeTrackLiteConnector) -> None:
    target = DeviceTarget(address="127.0.0.1", serial="DB-01")
    probe = await db_connector.probe(target)
    assert probe.model == "eTimeTrackLite DB"
    assert probe.extra.get("row_count") == 20

    health = await db_connector.health()
    assert health.reachable is True


@pytest.mark.asyncio
async def test_db_read_fetch_and_checkpoint(db_connector: ETimeTrackLiteConnector) -> None:
    # 1. Fetch all
    punches = [p async for p in db_connector.fetch_punches(Checkpoint())]
    assert len(punches) == 20
    assert punches[0].device_pin == "EMP100"

    # 2. Resume from checkpoint
    mid_time = punches[9].device_local_time.strftime("%Y-%m-%d %H:%M:%S")
    resumed = [p async for p in db_connector.fetch_punches(Checkpoint(cursor=mid_time))]
    assert len(resumed) == 10
    assert resumed[0].device_pin == "EMP110"


@pytest.mark.asyncio
async def test_db_read_write_operations_strictly_unsupported(db_connector: ETimeTrackLiteConnector) -> None:
    # Read-only guard
    with pytest.raises(Unsupported, match="read-only"):
        await db_connector.upsert_person(DevicePerson(pin="1", name="Test"))

    with pytest.raises(Unsupported, match="read-only"):
        await db_connector.delete_person("1")

    with pytest.raises(Unsupported, match="read-only"):
        await db_connector.set_time(datetime.now(UTC))

    with pytest.raises(Unsupported, match="read-only"):
        await db_connector.list_people()


@pytest.mark.asyncio
async def test_db_read_conformance(db_connector: ETimeTrackLiteConnector) -> None:
    target = DeviceTarget(address="127.0.0.1", serial="DB-01")
    result = await run_conformance(
        db_connector,
        target,
        capabilities=db_connector.CAPABILITIES,
        punch_count=20,
    )
    assert result.ok, f"db_read conformance failed: {result.failed}, errors: {result.errors}"
