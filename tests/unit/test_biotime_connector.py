"""Tests for ZKBioTime vendor connector adapter with mock server and conformance harness (ADR-002, M7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bip.connectors.biotime.adapter import BioTimeConnector
from bip.emulators.biotime_mock import create_biotime_mock_app
from bip.sdk.conformance import run_conformance
from bip.sdk.events import Checkpoint, DevicePerson, DeviceTarget


@pytest.fixture
def biotime_app():
    return create_biotime_mock_app()


@pytest.fixture
async def biotime_client(biotime_app):
    transport = httpx.ASGITransport(app=biotime_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def biotime_connector(biotime_client):
    return BioTimeConnector(
        base_url="http://testserver",
        token="biotime-mock-valid-token",
        client=biotime_client,
    )


@pytest.mark.asyncio
async def test_biotime_probe_and_health(biotime_connector: BioTimeConnector) -> None:
    target = DeviceTarget(address="biotime.school.local", serial="BIOTIME-SRV-01")
    probe = await biotime_connector.probe(target)
    assert probe.model == "ZKBioTime Server"
    assert len(probe.capabilities) >= 4

    health = await biotime_connector.health()
    assert health.reachable is True


@pytest.mark.asyncio
async def test_biotime_people_crud(biotime_connector: BioTimeConnector) -> None:
    # 1. Upsert
    p = DevicePerson(pin="3001", name="Kavita Reddy", card_no="99881122")
    up_res = await biotime_connector.upsert_person(p)
    assert up_res.success is True

    # 2. List
    people = await biotime_connector.list_people()
    assert len(people) == 1
    assert people[0].pin == "3001"
    assert people[0].name == "Kavita Reddy"

    # 3. Delete
    del_res = await biotime_connector.delete_person("3001")
    assert del_res.success is True

    # 4. Verify deleted
    people_after = await biotime_connector.list_people()
    assert len(people_after) == 0


@pytest.mark.asyncio
async def test_biotime_fetch_and_checkpoint(
    biotime_connector: BioTimeConnector, biotime_client: httpx.AsyncClient
) -> None:
    base = datetime(2026, 10, 20, 10, 0, 0)
    for i in range(10):
        t_str = (base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        await biotime_client.post(
            "/mock/add_transaction",
            json={
                "emp_code": f"EMP-{i}",
                "punch_time": t_str,
                "verify_type": 1,
            },
        )

    punches = [p async for p in biotime_connector.fetch_punches(Checkpoint())]
    assert len(punches) == 10

    # Resume from checkpoint at #5
    cursor = (base + timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S")
    resumed = [p async for p in biotime_connector.fetch_punches(Checkpoint(cursor=cursor))]
    assert len(resumed) == 5
    assert resumed[0].device_pin == "EMP-5"


@pytest.mark.asyncio
async def test_biotime_conformance(
    biotime_connector: BioTimeConnector, biotime_client: httpx.AsyncClient
) -> None:
    base = datetime.now(UTC) - timedelta(hours=4)
    for i in range(25):
        t_str = (base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        await biotime_client.post(
            "/mock/add_transaction",
            json={"emp_code": f"CONF-{i}", "punch_time": t_str, "verify_type": 1},
        )

    target = DeviceTarget(address="biotime.example.com", serial="BIOTIME-01")
    result = await run_conformance(
        biotime_connector,
        target,
        capabilities=biotime_connector.CAPABILITIES,
        punch_count=25,
    )
    assert result.ok, f"BioTime conformance failed: {result.failed}, errors: {result.errors}"
