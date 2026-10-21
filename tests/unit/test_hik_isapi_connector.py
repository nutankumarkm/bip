"""Tests for Hikvision ISAPI connector adapter with mock server and conformance harness (ADR-002, M7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bip.connectors.hik_isapi.adapter import HikvisionISAPIConnector
from bip.emulators.hik_isapi_mock import create_hik_isapi_mock_app
from bip.sdk.conformance import run_conformance
from bip.sdk.events import Checkpoint, DevicePerson, DeviceTarget


@pytest.fixture
def mock_app():
    return create_hik_isapi_mock_app(serial="HIK-TEST-SERIAL-1", model="DS-K1T671MF")


@pytest.fixture
async def async_client(mock_app):
    transport = httpx.ASGITransport(app=mock_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def hik_connector(async_client):
    target = DeviceTarget(address="192.168.1.50", port=80, serial="HIK-TEST-SERIAL-1")
    return HikvisionISAPIConnector(target=target, client=async_client)


@pytest.mark.asyncio
async def test_hik_isapi_probe(hik_connector: HikvisionISAPIConnector) -> None:
    probe = await hik_connector.probe(hik_connector.target)
    assert probe.serial == "HIK-TEST-SERIAL-1"
    assert "DS-K1T671MF" in (probe.model or "")
    assert len(probe.capabilities) >= 5


@pytest.mark.asyncio
async def test_hik_isapi_health(hik_connector: HikvisionISAPIConnector) -> None:
    health = await hik_connector.health()
    assert health.reachable is True
    assert health.drift_seconds is not None


@pytest.mark.asyncio
async def test_hik_isapi_people_crud(hik_connector: HikvisionISAPIConnector) -> None:
    # 1. Upsert
    p = DevicePerson(pin="2001", name="Anita Desai")
    up_res = await hik_connector.upsert_person(p)
    assert up_res.success is True

    # 2. List
    people = await hik_connector.list_people()
    assert len(people) == 1
    assert people[0].pin == "2001"
    assert people[0].name == "Anita Desai"

    # 3. Delete
    del_res = await hik_connector.delete_person("2001")
    assert del_res.success is True

    # 4. Verify deleted
    people_after = await hik_connector.list_people()
    assert len(people_after) == 0


@pytest.mark.asyncio
async def test_hik_isapi_fetch_and_checkpoint(
    hik_connector: HikvisionISAPIConnector, async_client: httpx.AsyncClient
) -> None:
    base_time = datetime(2026, 10, 20, 9, 0, 0)
    for i in range(10):
        t_str = (base_time + timedelta(minutes=i)).isoformat()
        await async_client.post(
            "/mock/add_event",
            json={
                "major": 5,
                "minor": 75,
                "time": t_str,
                "employeeNoString": f"PIN-{i}",
            },
        )

    # Fetch all
    punches = [p async for p in hik_connector.fetch_punches(Checkpoint())]
    assert len(punches) == 10

    # Resume from checkpoint at #5
    cursor = (base_time + timedelta(minutes=4)).isoformat()
    resumed = [p async for p in hik_connector.fetch_punches(Checkpoint(cursor=cursor))]
    assert len(resumed) == 5
    assert resumed[0].device_pin == "PIN-5"


@pytest.mark.asyncio
async def test_hik_isapi_conformance(
    hik_connector: HikvisionISAPIConnector, async_client: httpx.AsyncClient
) -> None:
    # Seed events for conformance tests
    base = datetime.now(UTC) - timedelta(hours=3)
    for i in range(30):
        await async_client.post(
            "/mock/add_event",
            json={
                "major": 5,
                "minor": 75,
                "time": (base + timedelta(minutes=i)).isoformat(),
                "employeeNoString": f"CONF-{i}",
            },
        )

    target = DeviceTarget(address="192.168.1.50", port=80, serial="HIK-TEST-SERIAL-1")
    result = await run_conformance(
        hik_connector,
        target,
        capabilities=hik_connector.CAPABILITIES,
        punch_count=30,
    )
    assert result.ok, f"Hikvision conformance failed: {result.failed}, errors: {result.errors}"
