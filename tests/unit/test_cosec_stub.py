"""Tests for Matrix COSEC stub connector (ADR-002, section 8.5, M7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bip.connectors.cosec.adapter import MatrixCosecConnector
from bip.sdk.errors import Unsupported
from bip.sdk.events import Checkpoint, DevicePerson, DeviceTarget


@pytest.fixture
def cosec_connector():
    return MatrixCosecConnector()


@pytest.mark.asyncio
async def test_cosec_connector_stub_behavior(cosec_connector: MatrixCosecConnector) -> None:
    # 1. Capabilities must be empty
    assert len(cosec_connector.CAPABILITIES) == 0

    # 2. Probe returns stub info
    target = DeviceTarget(address="192.168.1.10", serial="COSEC-01")
    probe = await cosec_connector.probe(target)
    assert probe.model == "Matrix COSEC (Stub)"
    assert probe.capabilities == []

    # 3. Health reports stub status
    health = await cosec_connector.health()
    assert health.reachable is False
    assert health.extra.get("status") == "stub_only"

    # 4. Pull punches raises Unsupported
    with pytest.raises(Unsupported, match="stub"):
        async for _ in cosec_connector.fetch_punches(Checkpoint()):
            pass

    # 5. People CRUD and time set raise Unsupported
    with pytest.raises(Unsupported):
        await cosec_connector.list_people()

    with pytest.raises(Unsupported):
        await cosec_connector.upsert_person(DevicePerson(pin="1", name="Test"))

    with pytest.raises(Unsupported):
        await cosec_connector.delete_person("1")

    with pytest.raises(Unsupported):
        await cosec_connector.set_time(datetime.now(UTC))
