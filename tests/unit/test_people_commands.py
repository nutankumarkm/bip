"""Tests for People, Commands, Enrolments, Match Suggestions, and Reconciliation (M5)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.auth import clear_clients, clear_orgs, register_client
from bip.api.routes.v1 import add_test_enrolment, add_test_punch, reset_stores


@pytest.fixture(autouse=True)
def setup_api():
    clear_clients()
    clear_orgs()
    reset_stores()
    register_client(
        "test-client",
        "test-secret",
        "partner-1",
        [
            "orgs:write",
            "devices:read",
            "devices:write",
            "people:write",
            "punches:read",
            "commands:write",
            "webhooks:write",
            "imports:write",
        ],
    )
    yield


def _get_token(client: TestClient) -> str:
    resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "test-client",
            "client_secret": "test-secret",
        },
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_token(client)}"}


def _create_org_and_site(c: TestClient, headers: dict) -> tuple[str, str]:
    org = c.post("/v1/orgs", json={"type": "school", "name": "Test School"}, headers=headers).json()
    site = c.post(f"/v1/orgs/{org['id']}/sites", json={"name": "Main Campus"}, headers=headers).json()
    return org["id"], site["id"]


@pytest.mark.unit
class TestPeople:
    def test_upsert_person_creates_with_pin(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        resp = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "person_type": "student", "site_ids": [site_id]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_ref"] == "STU001"
        assert data["display_name"] == "Alice"
        assert "device_pin" in data
        assert data["device_pin"] == "10001"

    def test_upsert_person_allocates_sequential_pins(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        p1 = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        ).json()
        p2 = c.put(
            f"/v1/orgs/{org_id}/people/STU002",
            json={"display_name": "Bob", "site_ids": [site_id]},
            headers=headers,
        ).json()

        assert p1["device_pin"] == "10001"
        assert p2["device_pin"] == "10002"

    def test_upsert_person_update_preserves_pin(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        p1 = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        ).json()
        pin = p1["device_pin"]

        p2 = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice Updated", "site_ids": [site_id]},
            headers=headers,
        ).json()
        assert p2["device_pin"] == pin
        assert p2["display_name"] == "Alice Updated"

    def test_list_people(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.put(f"/v1/orgs/{org_id}/people/S1", json={"display_name": "A", "site_ids": [site_id]}, headers=headers)
        c.put(f"/v1/orgs/{org_id}/people/S2", json={"display_name": "B", "site_ids": [site_id]}, headers=headers)

        resp = c.get(f"/v1/orgs/{org_id}/people", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_people_filter_active(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.put(
            f"/v1/orgs/{org_id}/people/S1",
            json={"display_name": "Active", "active": True, "site_ids": [site_id]},
            headers=headers,
        )
        c.put(
            f"/v1/orgs/{org_id}/people/S2",
            json={"display_name": "Inactive", "active": False, "site_ids": [site_id]},
            headers=headers,
        )

        active = c.get(f"/v1/orgs/{org_id}/people?active=true", headers=headers).json()
        assert len(active) == 1
        assert active[0]["display_name"] == "Active"

    def test_list_people_filter_site(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        site2 = c.post(f"/v1/orgs/{org_id}/sites", json={"name": "Branch"}, headers=headers).json()

        c.put(f"/v1/orgs/{org_id}/people/S1", json={"display_name": "A", "site_ids": [site_id]}, headers=headers)
        c.put(f"/v1/orgs/{org_id}/people/S2", json={"display_name": "B", "site_ids": [site2["id"]]}, headers=headers)

        filtered = c.get(f"/v1/orgs/{org_id}/people?site_id={site_id}", headers=headers).json()
        assert len(filtered) == 1
        assert filtered[0]["display_name"] == "A"

    def test_get_person(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.put(
            f"/v1/orgs/{org_id}/people/STU001", json={"display_name": "Alice", "site_ids": [site_id]}, headers=headers
        )

        resp = c.get(f"/v1/orgs/{org_id}/people/STU001", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Alice"

    def test_get_person_not_found(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.get(f"/v1/orgs/{org_id}/people/NONEXISTENT", headers=headers)
        assert resp.status_code == 404

    def test_delete_person(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.put(
            f"/v1/orgs/{org_id}/people/STU001", json={"display_name": "Alice", "site_ids": [site_id]}, headers=headers
        )

        resp = c.delete(f"/v1/orgs/{org_id}/people/STU001", headers=headers)
        assert resp.status_code == 204

        resp = c.get(f"/v1/orgs/{org_id}/people/STU001", headers=headers)
        assert resp.status_code == 404

    def test_delete_person_not_found(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.delete(f"/v1/orgs/{org_id}/people/NONEXISTENT", headers=headers)
        assert resp.status_code == 404

    def test_upsert_with_card_no(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        resp = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "card_no": "CARD-1234", "site_ids": [site_id]},
            headers=headers,
        ).json()
        assert resp["card_no"] == "CARD-1234"


@pytest.mark.unit
class TestCommandFanOut:
    def test_upsert_person_creates_set_user_commands(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "DEV1", "site_id": site_id},
            headers=headers,
        )

        c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        )

        cmds = c.get(f"/v1/orgs/{org_id}/commands", headers=headers).json()
        set_user_cmds = [cmd for cmd in cmds if cmd["type"] == "set_user"]
        assert len(set_user_cmds) == 1
        assert set_user_cmds[0]["params"]["name"] == "Alice"

    def test_delete_person_creates_delete_user_commands(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "DEV1", "site_id": site_id},
            headers=headers,
        )

        c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        )

        c.delete(f"/v1/orgs/{org_id}/people/STU001", headers=headers)

        cmds = c.get(f"/v1/orgs/{org_id}/commands", headers=headers).json()
        del_cmds = [cmd for cmd in cmds if cmd["type"] == "delete_user"]
        assert len(del_cmds) == 1

    def test_fan_out_multiple_devices(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        for i in range(3):
            c.post(
                f"/v1/orgs/{org_id}/devices",
                json={"vendor": "ZKTeco", "family": "zk_adms", "serial": f"DEV{i}", "site_id": site_id},
                headers=headers,
            )

        c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        )

        cmds = c.get(f"/v1/orgs/{org_id}/commands", headers=headers).json()
        set_user_cmds = [cmd for cmd in cmds if cmd["type"] == "set_user"]
        assert len(set_user_cmds) == 3


@pytest.mark.unit
class TestCommands:
    def test_create_command(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "DEV1", "site_id": site_id},
            headers=headers,
        ).json()

        resp = c.post(
            f"/v1/orgs/{org_id}/commands",
            json={"device_id": dev["id"], "type": "reboot", "params": {}},
            headers=headers,
        )
        assert resp.status_code == 201
        cmd = resp.json()
        assert cmd["type"] == "reboot"
        assert cmd["state"] == "queued"

    def test_idempotency_key_dedupes(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "DEV1", "site_id": site_id},
            headers=headers,
        ).json()

        body = {"device_id": dev["id"], "type": "reboot", "idempotency_key": "idem-1"}
        r1 = c.post(f"/v1/orgs/{org_id}/commands", json=body, headers=headers).json()
        r2 = c.post(f"/v1/orgs/{org_id}/commands", json=body, headers=headers).json()
        assert r1["id"] == r2["id"]

    def test_list_commands_by_device(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        dev1 = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()
        dev2 = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D2", "site_id": site_id},
            headers=headers,
        ).json()

        c.post(f"/v1/orgs/{org_id}/commands", json={"device_id": dev1["id"], "type": "reboot"}, headers=headers)
        c.post(f"/v1/orgs/{org_id}/commands", json={"device_id": dev2["id"], "type": "clear_log"}, headers=headers)

        dev1_cmds = c.get(f"/v1/orgs/{org_id}/commands?device_id={dev1['id']}", headers=headers).json()
        assert len(dev1_cmds) == 1
        assert dev1_cmds[0]["type"] == "reboot"

    def test_list_commands_by_state(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        c.post(f"/v1/orgs/{org_id}/commands", json={"device_id": dev["id"], "type": "reboot"}, headers=headers)

        queued = c.get(f"/v1/orgs/{org_id}/commands?state=queued", headers=headers).json()
        assert len(queued) == 1

        sent = c.get(f"/v1/orgs/{org_id}/commands?state=sent", headers=headers).json()
        assert len(sent) == 0

    def test_get_command(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        cmd = c.post(
            f"/v1/orgs/{org_id}/commands",
            json={"device_id": dev["id"], "type": "set_time"},
            headers=headers,
        ).json()

        resp = c.get(f"/v1/orgs/{org_id}/commands/{cmd['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["type"] == "set_time"

    def test_get_command_not_found(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.get(f"/v1/orgs/{org_id}/commands/nonexistent-id", headers=headers)
        assert resp.status_code == 404

    def test_command_to_unknown_device_fails(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.post(
            f"/v1/orgs/{org_id}/commands",
            json={"device_id": "no-such-device", "type": "reboot"},
            headers=headers,
        )
        assert resp.status_code == 404


@pytest.mark.unit
class TestEnrolments:
    def test_list_person_enrolments(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        person = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        ).json()
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        add_test_enrolment(person["id"], dev["id"], fingerprints=2, face=True)

        resp = c.get(f"/v1/orgs/{org_id}/people/STU001/enrolments", headers=headers)
        assert resp.status_code == 200
        enrolments = resp.json()
        assert len(enrolments) == 1
        assert enrolments[0]["fingerprints"] == 2
        assert enrolments[0]["face"] is True

    def test_list_device_enrolments(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        p1 = c.put(
            f"/v1/orgs/{org_id}/people/S1", json={"display_name": "A", "site_ids": [site_id]}, headers=headers
        ).json()
        p2 = c.put(
            f"/v1/orgs/{org_id}/people/S2", json={"display_name": "B", "site_ids": [site_id]}, headers=headers
        ).json()
        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        add_test_enrolment(p1["id"], dev["id"], fingerprints=1)
        add_test_enrolment(p2["id"], dev["id"], face=True)

        resp = c.get(f"/v1/orgs/{org_id}/devices/{dev['id']}/enrolments", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_person_enrolments_not_found(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.get(f"/v1/orgs/{org_id}/people/NONEXISTENT/enrolments", headers=headers)
        assert resp.status_code == 404


@pytest.mark.unit
class TestMatchSuggestions:
    def test_no_suggestions_when_all_mapped(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _site_id = _create_org_and_site(c, headers)

        resp = c.get(f"/v1/orgs/{org_id}/match-suggestions", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_suggestions_returned_for_unmapped(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        person = c.put(
            f"/v1/orgs/{org_id}/people/STU001",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        ).json()

        now = datetime.now(UTC)
        add_test_punch(org_id, site_id, "dev-1", person["device_pin"], now)

        resp = c.get(f"/v1/orgs/{org_id}/match-suggestions", headers=headers)
        data = resp.json()
        assert len(data) == 1
        assert data[0]["score"] == 1.0
        assert data[0]["reason"] == "pin_match"


@pytest.mark.unit
class TestReconciliation:
    def test_reconcile_empty_device(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        resp = c.post(
            f"/v1/orgs/{org_id}/reconcile",
            json={"device_id": dev["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["in_sync"] is True
        assert data["expected_count"] == 0

    def test_reconcile_missing_people(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        c.put(
            f"/v1/orgs/{org_id}/people/S1",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        )

        resp = c.post(
            f"/v1/orgs/{org_id}/reconcile",
            json={"device_id": dev["id"]},
            headers=headers,
        )
        data = resp.json()
        assert data["in_sync"] is False
        assert data["expected_count"] == 1
        assert data["enrolled_count"] == 0
        assert len(data["missing"]) == 1

    def test_reconcile_in_sync(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        person = c.put(
            f"/v1/orgs/{org_id}/people/S1",
            json={"display_name": "Alice", "site_ids": [site_id]},
            headers=headers,
        ).json()

        add_test_enrolment(person["id"], dev["id"], fingerprints=2)

        resp = c.post(
            f"/v1/orgs/{org_id}/reconcile",
            json={"device_id": dev["id"]},
            headers=headers,
        )
        data = resp.json()
        assert data["in_sync"] is True
        assert data["expected_count"] == 1
        assert data["enrolled_count"] == 1

    def test_reconcile_extra_enrolments(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, site_id = _create_org_and_site(c, headers)

        dev = c.post(
            f"/v1/orgs/{org_id}/devices",
            json={"vendor": "ZKTeco", "family": "zk_adms", "serial": "D1", "site_id": site_id},
            headers=headers,
        ).json()

        add_test_enrolment("ghost-person-id", dev["id"], fingerprints=1)

        resp = c.post(
            f"/v1/orgs/{org_id}/reconcile",
            json={"device_id": dev["id"]},
            headers=headers,
        )
        data = resp.json()
        assert data["in_sync"] is False
        assert len(data["extra"]) == 1

    def test_reconcile_unknown_device_fails(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org_id, _ = _create_org_and_site(c, headers)

        resp = c.post(
            f"/v1/orgs/{org_id}/reconcile",
            json={"device_id": "no-such-device"},
            headers=headers,
        )
        assert resp.status_code == 404
