"""Tests for ZK TCP connector adapter with FakeZKClient emulator and conformance harness (ADR-002, M6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bip.connectors.zk_tcp.adapter import ZKConnector
from bip.emulators.fake_zk import FakeZKClient
from bip.sdk.conformance import run_conformance
from bip.sdk.events import Checkpoint, DevicePerson, DeviceTarget


@pytest.fixture
def fake_client() -> FakeZKClient:
    return FakeZKClient(ip="192.168.1.100", port=4370)


@pytest.fixture
def zk_connector(fake_client: FakeZKClient) -> ZKConnector:
    target = DeviceTarget(address="192.168.1.100", port=4370)
    return ZKConnector(target=target, client_factory=lambda **kwargs: fake_client)


@pytest.mark.asyncio
async def test_zk_connector_probe(zk_connector: ZKConnector) -> None:
    probe = await zk_connector.probe(zk_connector.target)
    assert probe.serial == "ZK-FAKE-998877"
    assert "Ver 6.60" in (probe.firmware or "")
    assert len(probe.capabilities) >= 5


@pytest.mark.asyncio
async def test_zk_connector_health(zk_connector: ZKConnector, fake_client: FakeZKClient) -> None:
    # Add some records to check log fill calculation
    for i in range(100):
        fake_client.add_punch(user_id=str(i), timestamp=datetime.now(UTC))

    health = await zk_connector.health()
    assert health.reachable is True
    assert health.serial == "ZK-FAKE-998877"
    assert health.log_fill_pct is not None
    assert health.drift_seconds is not None


@pytest.mark.asyncio
async def test_zk_connector_user_crud(zk_connector: ZKConnector) -> None:
    # 1. Upsert
    person = DevicePerson(pin="1001", name="Ravi Kumar", card_no="12345678", privilege=0)
    upsert_res = await zk_connector.upsert_person(person)
    assert upsert_res.success is True

    # 2. List
    people = await zk_connector.list_people()
    assert len(people) == 1
    assert people[0].pin == "1001"
    assert people[0].name == "Ravi Kumar"
    assert people[0].card_no == "12345678"

    # 3. Delete
    del_res = await zk_connector.delete_person("1001")
    assert del_res.success is True

    # 4. Verify deleted
    people_after = await zk_connector.list_people()
    assert len(people_after) == 0


@pytest.mark.asyncio
async def test_zk_connector_set_time(zk_connector: ZKConnector) -> None:
    now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
    res = await zk_connector.set_time(now)
    assert res.success is True

    health = await zk_connector.health()
    assert health.time is not None
    assert health.time.year == 2026


@pytest.mark.asyncio
async def test_zk_connector_fetch_punches_and_checkpoint_resume(
    zk_connector: ZKConnector, fake_client: FakeZKClient
) -> None:
    base_time = datetime(2026, 10, 20, 8, 0, 0)
    for i in range(10):
        fake_client.add_punch(user_id=f"PIN-{i}", timestamp=base_time + timedelta(minutes=i))

    # Fetch from start
    all_punches = [p async for p in zk_connector.fetch_punches(Checkpoint())]
    assert len(all_punches) == 10

    # Resume from checkpoint at punch #5
    mid_time = (base_time + timedelta(minutes=4)).isoformat()
    resumed_punches = [p async for p in zk_connector.fetch_punches(Checkpoint(cursor=mid_time))]
    assert len(resumed_punches) == 5
    assert resumed_punches[0].device_pin == "PIN-5"
    assert resumed_punches[-1].device_pin == "PIN-9"


@pytest.mark.asyncio
async def test_zk_connector_conformance_harness(zk_connector: ZKConnector, fake_client: FakeZKClient) -> None:
    """Run the official SDK conformance harness against ZKConnector."""
    # Seed punches for conformance punch tests
    base = datetime.now(UTC) - timedelta(hours=5)
    for i in range(50):
        fake_client.add_punch(user_id=f"CONF-{i}", timestamp=base + timedelta(minutes=i))

    target = DeviceTarget(address="192.168.1.100", port=4370)
    result = await run_conformance(
        zk_connector,
        target,
        capabilities=zk_connector.CAPABILITIES,
        punch_count=50,
    )

    assert result.ok, f"Conformance failures: {result.failed}, errors: {result.errors}"
    assert "probe_returns_probe_result" in result.passed
    assert "health_returns_health_report" in result.passed
    assert "fetch_punches_from_start" in result.passed
    assert "resume_no_duplicates" in result.passed
    assert "upsert_person" in result.passed
    assert "upsert_then_read_round_trip" in result.passed
    assert "delete_person" in result.passed
