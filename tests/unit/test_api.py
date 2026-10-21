"""Tests for Consumer API v1."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.auth import clear_clients, clear_orgs, register_client, register_org
from bip.api.routes.v1 import add_test_punch, reset_stores


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


@pytest.mark.unit
class TestOAuth:
    def test_valid_credentials(self):
        c = TestClient(app)
        resp = c.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-client",
                "client_secret": "test-secret",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_invalid_credentials(self):
        c = TestClient(app)
        resp = c.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test-client",
                "client_secret": "wrong-secret",
            },
        )
        assert resp.status_code == 401

    def test_wrong_grant_type(self):
        c = TestClient(app)
        resp = c.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "test-client",
                "client_secret": "test-secret",
            },
        )
        assert resp.status_code == 400


@pytest.mark.unit
class TestOrgs:
    def test_create_and_get_org(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        resp = c.post(
            "/v1/orgs",
            json={
                "type": "school",
                "name": "Test School",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        org = resp.json()
        assert org["name"] == "Test School"

        resp = c.get(f"/v1/orgs/{org['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test School"

    def test_cross_partner_access_denied(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        register_org("other-org-id", "different-partner")
        resp = c.get("/v1/orgs/other-org-id", headers=headers)
        assert resp.status_code == 403


@pytest.mark.unit
class TestSites:
    def test_create_site(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        resp = c.post(f"/v1/orgs/{org['id']}/sites", json={"name": "Main"}, headers=headers)
        assert resp.status_code == 201
        assert resp.json()["name"] == "Main"


@pytest.mark.unit
class TestDevices:
    def test_register_device(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        site = c.post(f"/v1/orgs/{org['id']}/sites", json={"name": "Main"}, headers=headers).json()
        resp = c.post(
            f"/v1/orgs/{org['id']}/devices",
            json={
                "vendor": "ZKTeco",
                "family": "zk_adms",
                "serial": "ABC123",
                "mode": "push",
                "site_id": site["id"],
            },
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "expected"
        assert "onboarding" in data


@pytest.mark.unit
class TestPunches:
    def test_cursor_feed(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        org_id = org["id"]

        now = datetime.now(UTC)
        for i in range(10):
            add_test_punch(org_id, "site-1", "dev-1", str(10001 + i), now)

        resp = c.get(f"/v1/orgs/{org_id}/punches?cursor=0&limit=5", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 5
        cursor = data["next_cursor"]

        resp = c.get(f"/v1/orgs/{org_id}/punches?cursor={cursor}&limit=5", headers=headers)
        data = resp.json()
        assert len(data["items"]) == 5

    def test_cursor_returns_all_punches_exactly_once(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        org_id = org["id"]

        now = datetime.now(UTC)
        for i in range(25):
            add_test_punch(org_id, "site-1", "dev-1", str(10001 + i), now)

        all_punches = []
        cursor = 0
        for _ in range(10):
            resp = c.get(f"/v1/orgs/{org_id}/punches?cursor={cursor}&limit=10", headers=headers)
            data = resp.json()
            items = data["items"]
            if not items:
                break
            all_punches.extend(items)
            cursor = data["next_cursor"]

        assert len(all_punches) == 25
        seqs = [p["seq"] for p in all_punches]
        assert len(set(seqs)) == 25

    def test_unmapped_pins(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        org_id = org["id"]

        now = datetime.now(UTC)
        add_test_punch(org_id, "site-1", "dev-1", "99999", now)
        add_test_punch(org_id, "site-1", "dev-1", "99999", now)

        resp = c.get(f"/v1/orgs/{org_id}/unmapped-pins", headers=headers)
        assert resp.status_code == 200
        pins = resp.json()
        assert len(pins) == 1
        assert pins[0]["device_pin"] == "99999"
        assert pins[0]["count"] == 2


@pytest.mark.unit
class TestWebhooks:
    def test_create_and_list_webhooks(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        org_id = org["id"]

        resp = c.post(
            f"/v1/orgs/{org_id}/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["punch.created"],
            },
            headers=headers,
        )
        assert resp.status_code == 201
        wh = resp.json()
        assert "secret" in wh

        resp = c.get(f"/v1/orgs/{org_id}/webhooks", headers=headers)
        assert len(resp.json()) == 1

    def test_delete_webhook(self):
        c = TestClient(app)
        headers = _auth_headers(c)
        org = c.post("/v1/orgs", json={"type": "school", "name": "S"}, headers=headers).json()
        org_id = org["id"]

        wh = c.post(
            f"/v1/orgs/{org_id}/webhooks",
            json={
                "url": "https://example.com/hook",
                "events": ["punch.created"],
            },
            headers=headers,
        ).json()

        resp = c.delete(f"/v1/orgs/{org_id}/webhooks/{wh['id']}", headers=headers)
        assert resp.status_code == 204

        assert len(c.get(f"/v1/orgs/{org_id}/webhooks", headers=headers).json()) == 0
