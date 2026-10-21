"""Unit tests for the BIP SDK."""

from datetime import UTC, datetime

import pytest

from bip.sdk import (
    Capability,
    ConnectorError,
    DeviceCommand,
    DevicePerson,
    ParsedUpload,
    PunchEvent,
    RawPunch,
    Unsupported,
    compute_dedupe_key,
)
from bip.sdk.conformance import ConformanceResult


@pytest.mark.unit
class TestCapabilities:
    def test_all_capabilities_are_strings(self):
        for cap in Capability:
            assert isinstance(cap, str)
            assert "." in cap

    def test_capability_count(self):
        assert len(Capability) == 11

    def test_templates_relay_exists(self):
        assert Capability.TEMPLATES_RELAY == "templates.relay"

    def test_logs_clear_exists(self):
        assert Capability.LOGS_CLEAR == "logs.clear"


@pytest.mark.unit
class TestPunchEvent:
    def test_create_punch_event(self):
        now = datetime.now(UTC)
        event = PunchEvent(
            org_id="org-1",
            site_id="site-1",
            device_id="dev-1",
            device_pin="10001",
            device_local_time=now,
            occurred_at=now,
            verify_mode="fingerprint",
            source="adms",
        )
        assert event.device_pin == "10001"
        assert event.verify_mode == "fingerprint"
        assert event.person_id is None

    def test_dedupe_key_computation(self):
        now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
        event = PunchEvent(
            org_id="org-1",
            site_id="site-1",
            device_id="dev-1",
            device_pin="10001",
            device_local_time=now,
            occurred_at=now,
            verify_mode="fingerprint",
            source="adms",
        )
        key = event.compute_dedupe_key("SERIAL123")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_dedupe_key_deterministic(self):
        now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
        event = PunchEvent(
            org_id="org-1",
            site_id="site-1",
            device_id="dev-1",
            device_pin="10001",
            device_local_time=now,
            occurred_at=now,
            verify_mode="fingerprint",
            source="adms",
        )
        key1 = event.compute_dedupe_key("SERIAL123")
        key2 = event.compute_dedupe_key("SERIAL123")
        assert key1 == key2

    def test_dedupe_key_varies_by_serial(self):
        now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
        event = PunchEvent(
            org_id="org-1",
            site_id="site-1",
            device_id="dev-1",
            device_pin="10001",
            device_local_time=now,
            occurred_at=now,
            verify_mode="fingerprint",
            source="adms",
        )
        key1 = event.compute_dedupe_key("SERIAL123")
        key2 = event.compute_dedupe_key("SERIAL456")
        assert key1 != key2

    def test_with_dedupe(self):
        now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
        event = PunchEvent(
            org_id="org-1",
            site_id="site-1",
            device_id="dev-1",
            device_pin="10001",
            device_local_time=now,
            occurred_at=now,
            verify_mode="fingerprint",
            source="adms",
        )
        deduped = event.with_dedupe("SERIAL123")
        assert deduped.dedupe_key != ""
        assert deduped.device_pin == "10001"


@pytest.mark.unit
class TestDedupe:
    def test_compute_dedupe_key(self):
        key = compute_dedupe_key("SERIAL123", "10001", "2026-10-21 10:30:00", "fingerprint")
        assert isinstance(key, str)
        assert len(key) == 64

    def test_same_inputs_same_key(self):
        key1 = compute_dedupe_key("S1", "100", "2026-01-01 00:00:00", "face")
        key2 = compute_dedupe_key("S1", "100", "2026-01-01 00:00:00", "face")
        assert key1 == key2

    def test_different_verify_mode_different_key(self):
        key1 = compute_dedupe_key("S1", "100", "2026-01-01 00:00:00", "face")
        key2 = compute_dedupe_key("S1", "100", "2026-01-01 00:00:00", "card")
        assert key1 != key2


@pytest.mark.unit
class TestErrors:
    def test_error_hierarchy(self):
        assert issubclass(Unsupported, ConnectorError)

    def test_error_problem_type(self):
        e = Unsupported("Not supported")
        assert e.problem_type == "capability_unsupported"

    def test_error_device_id(self):
        e = Unsupported("test", device_id="dev-123")
        assert e.device_id == "dev-123"


@pytest.mark.unit
class TestProtocols:
    def test_device_command(self):
        cmd = DeviceCommand(cmd_no=1, type="user_update", params={"pin": "100"})
        assert cmd.cmd_no == 1
        assert cmd.type == "user_update"

    def test_parsed_upload_defaults(self):
        pu = ParsedUpload()
        assert pu.punches == []
        assert pu.users == []
        assert pu.enrolment_counts == {}

    def test_parsed_upload_with_data(self):
        now = datetime.now(UTC)
        punch = RawPunch(device_pin="100", device_local_time=now)
        user = DevicePerson(pin="100", name="Test")
        pu = ParsedUpload(punches=[punch], users=[user])
        assert len(pu.punches) == 1
        assert len(pu.users) == 1


@pytest.mark.unit
class TestConformanceResult:
    def test_ok_when_no_failures(self):
        r = ConformanceResult(connector_family="test")
        r.passed.append("test1")
        assert r.ok

    def test_not_ok_when_failures(self):
        r = ConformanceResult(connector_family="test")
        r.failed.append("test1")
        assert not r.ok
