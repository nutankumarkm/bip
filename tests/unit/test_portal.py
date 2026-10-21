"""Unit tests for the org-level portal (auth + all routes)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.portal.auth import (
    PORTAL_SESSION_COOKIE,
    clear_portal_state,
    create_portal_user,
)
from bip.api.routes.v1 import reset_stores


@pytest.fixture(autouse=True)
def _clean():
    clear_portal_state()
    reset_stores()
    yield
    clear_portal_state()
    reset_stores()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def org_id(client):
    """Create a seed org and return its id."""
    from bip.api.routes.v1 import _orgs
    import uuid, datetime
    oid = str(uuid.uuid4())
    _orgs[oid] = {
        "id": oid, "name": "Test School",
        "pin_range_start": 5001, "timezone": "UTC",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    return oid


@pytest.fixture()
def portal_session(client, org_id):
    """Create a portal user and return an authenticated TestClient."""
    create_portal_user("admin@school.test", "SecurePass1!", org_id, display_name="School Admin")
    resp = client.post(
        "/portal/login",
        data={"email": "admin@school.test", "password": "SecurePass1!"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"Expected 303, got {resp.status_code}: {resp.text[:200]}"
    token = resp.cookies.get(PORTAL_SESSION_COOKIE)
    assert token, "No session cookie after login"
    authed = TestClient(app, raise_server_exceptions=True, cookies={PORTAL_SESSION_COOKIE: token})
    return authed


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


class TestPortalAuth:
    def test_login_page_renders(self, client):
        resp = client.get("/portal/login")
        assert resp.status_code == 200
        assert "Organisation Portal" in resp.text

    def test_login_success_redirects(self, client, org_id):
        create_portal_user("u@test.test", "pass1234!", org_id)
        resp = client.post(
            "/portal/login",
            data={"email": "u@test.test", "password": "pass1234!"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/portal/"

    def test_login_sets_cookie(self, client, org_id):
        create_portal_user("u@test.test", "pass1234!", org_id)
        resp = client.post("/portal/login", data={"email": "u@test.test", "password": "pass1234!"})
        assert PORTAL_SESSION_COOKIE in resp.cookies or PORTAL_SESSION_COOKIE in client.cookies

    def test_login_bad_password_401(self, client, org_id):
        create_portal_user("u@test.test", "correct_pass!", org_id)
        resp = client.post("/portal/login", data={"email": "u@test.test", "password": "wrong!"})
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.text

    def test_login_unknown_user_401(self, client):
        resp = client.post("/portal/login", data={"email": "nobody@x.test", "password": "x"})
        assert resp.status_code == 401

    def test_logout_clears_session(self, client, org_id):
        create_portal_user("u@test.test", "pass1234!", org_id)
        client.post("/portal/login", data={"email": "u@test.test", "password": "pass1234!"})
        resp = client.get("/portal/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/portal/login"


# ---------------------------------------------------------------------------
# Unauthenticated redirects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", [
    "/portal/",
    "/portal/attendance",
    "/portal/people",
    "/portal/devices",
    "/portal/sites",
])
def test_unauthenticated_redirects_to_login(client, path):
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert "/portal/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Authenticated pages
# ---------------------------------------------------------------------------


class TestPortalPages:
    def test_dashboard_renders(self, portal_session):
        resp = portal_session.get("/portal/")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_shows_org_name(self, portal_session):
        resp = portal_session.get("/portal/")
        assert "Test School" in resp.text

    def test_attendance_page_renders(self, portal_session):
        resp = portal_session.get("/portal/attendance")
        assert resp.status_code == 200
        assert "Attendance Feed" in resp.text

    def test_people_page_renders(self, portal_session):
        resp = portal_session.get("/portal/people")
        assert resp.status_code == 200
        assert "Roster" in resp.text

    def test_devices_page_renders(self, portal_session):
        resp = portal_session.get("/portal/devices")
        assert resp.status_code == 200
        assert "Devices" in resp.text

    def test_sites_page_renders(self, portal_session):
        resp = portal_session.get("/portal/sites")
        assert resp.status_code == 200
        assert "Sites" in resp.text


# ---------------------------------------------------------------------------
# People POST
# ---------------------------------------------------------------------------


class TestPortalPeople:
    def test_add_person_redirects(self, portal_session):
        resp = portal_session.post(
            "/portal/people",
            data={"display_name": "Jane Smith", "person_type": "student", "manual_pin": "", "card_no": "", "external_ref": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/portal/people" in resp.headers["location"]
        assert "Jane+Smith" in resp.headers["location"] or "Jane" in resp.headers["location"]

    def test_add_person_auto_pin(self, portal_session, org_id):
        from bip.api.routes.v1 import _people
        portal_session.post(
            "/portal/people",
            data={"display_name": "Bob Jones", "person_type": "employee", "manual_pin": "", "card_no": "", "external_ref": ""},
        )
        people = [p for p in _people.values() if p.get("display_name") == "Bob Jones"]
        assert len(people) == 1
        assert people[0]["pin"] == "5001"  # pin_range_start for this org

    def test_add_person_manual_pin(self, portal_session):
        from bip.api.routes.v1 import _people
        portal_session.post(
            "/portal/people",
            data={"display_name": "Alice", "person_type": "student", "manual_pin": "9999", "card_no": "", "external_ref": ""},
        )
        people = [p for p in _people.values() if p.get("display_name") == "Alice"]
        assert len(people) == 1
        assert people[0]["pin"] == "9999"

    def test_people_appear_in_list(self, portal_session):
        portal_session.post(
            "/portal/people",
            data={"display_name": "Charlie Brown", "person_type": "student", "manual_pin": "1234", "card_no": "", "external_ref": ""},
        )
        resp = portal_session.get("/portal/people")
        assert "Charlie Brown" in resp.text
        assert "1234" in resp.text


# ---------------------------------------------------------------------------
# Ops portal-users management
# ---------------------------------------------------------------------------


class TestOpsPortalUsers:
    def _ops_session(self, client):
        """Quick-login to ops console."""
        resp = client.post("/ops/quick-login", follow_redirects=False)
        from bip.api.ops.auth import SESSION_COOKIE
        token = resp.cookies.get(SESSION_COOKIE)
        return TestClient(app, raise_server_exceptions=True, cookies={SESSION_COOKIE: token})

    def test_portal_users_page_renders(self, client):
        ops = self._ops_session(client)
        resp = ops.get("/ops/portal-users")
        assert resp.status_code == 200
        assert "Portal Users" in resp.text

    def test_create_portal_user_via_ops(self, client, org_id):
        ops = self._ops_session(client)
        # get CSRF
        resp = ops.get("/ops/portal-users")
        from html.parser import HTMLParser
        class CSRFScraper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.token = ""
            def handle_starttag(self, tag, attrs):
                if tag == "input":
                    d = dict(attrs)
                    if d.get("name") == "csrf_token":
                        self.token = d.get("value", "")
        s = CSRFScraper()
        s.feed(resp.text)

        resp2 = ops.post(
            "/ops/portal-users",
            data={
                "email": "newuser@school.test",
                "password": "Secret1234!",
                "org_id": org_id,
                "display_name": "New Admin",
                "csrf_token": s.token or "test_csrf",
            },
            follow_redirects=False,
        )
        assert resp2.status_code == 303
        assert "newuser" in resp2.headers.get("location", "")

    def test_portal_user_can_login_after_ops_creation(self, client, org_id):
        ops = self._ops_session(client)
        resp = ops.get("/ops/portal-users")
        from html.parser import HTMLParser
        class CSRFScraper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.token = ""
            def handle_starttag(self, tag, attrs):
                if tag == "input":
                    d = dict(attrs)
                    if d.get("name") == "csrf_token":
                        self.token = d.get("value", "")
        s = CSRFScraper()
        s.feed(resp.text)
        ops.post(
            "/ops/portal-users",
            data={
                "email": "newuser@school.test",
                "password": "Secret1234!",
                "org_id": org_id,
                "display_name": "New Admin",
                "csrf_token": s.token or "test_csrf",
            },
        )
        # now try portal login
        resp3 = client.post(
            "/portal/login",
            data={"email": "newuser@school.test", "password": "Secret1234!"},
            follow_redirects=False,
        )
        assert resp3.status_code == 303
        assert resp3.headers["location"] == "/portal/"
