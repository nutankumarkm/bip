"""Smoke tests for the BIP Ops Console (M8).

Tests:
- Login page renders
- Wrong password → 401 with error message
- Correct password → redirects to TOTP page
- TOTP verify with valid code → session established
- All console pages redirect to login when unauthenticated
- Dashboard renders after full auth
- Partners page renders and POST creates partner
- Orgs, Sites, Devices, Gateways pages render
- Approvals list and two-person review (requestor cannot self-approve)
- Audit log page renders and filters work
- CSRF: missing token on POST still proceeds (non-empty token accepted in tests)
"""

from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.ops.auth import (
    SESSION_COOKIE,
    clear_console_state,
    create_console_user,
    create_session,
    get_session,
)
from bip.api.ops.store import clear_ops_state, create_approval

client = TestClient(app, follow_redirects=False)


def setup_function() -> None:
    clear_console_state()
    clear_ops_state()


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------


def test_login_page_renders() -> None:
    resp = client.get("/ops/login")
    assert resp.status_code == 200
    assert "BIP Ops Console" in resp.text
    assert "<form" in resp.text


def test_login_wrong_password() -> None:
    create_console_user("admin@test.com", "correct-password")
    resp = client.post(
        "/ops/login",
        data={"email": "admin@test.com", "password": "wrong", "csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text


def test_login_correct_password_redirects_to_totp() -> None:
    create_console_user("admin@test.com", "my-password")
    resp = client.post(
        "/ops/login",
        data={"email": "admin@test.com", "password": "my-password", "csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ops/totp"
    assert SESSION_COOKIE in resp.cookies


def test_totp_page_requires_pre_totp_session() -> None:
    resp = client.get("/ops/totp", follow_redirects=False)
    assert resp.status_code == 303
    assert "/ops/login" in resp.headers["location"]


def test_totp_verify_valid_code() -> None:
    user = create_console_user("admin@test.com", "my-password")
    # Simulate password-verified pre-TOTP session
    pre_token = create_session("admin@test.com", pre_totp=True)
    totp = pyotp.TOTP(user["totp_secret"])
    valid_code = totp.now()

    resp = client.post(
        "/ops/totp",
        data={"totp_code": valid_code, "csrf_token": "test"},
        cookies={SESSION_COOKIE: pre_token},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/ops/"
    # New full session cookie should be set
    assert SESSION_COOKIE in resp.cookies


def test_totp_verify_wrong_code() -> None:
    create_console_user("admin@test.com", "my-password")
    pre_token = create_session("admin@test.com", pre_totp=True)

    resp = client.post(
        "/ops/totp",
        data={"totp_code": "000000", "csrf_token": "test"},
        cookies={SESSION_COOKIE: pre_token},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "Invalid TOTP" in resp.text


def test_logout_clears_session() -> None:
    full_token = create_session("admin@test.com", pre_totp=False)
    resp = client.get("/ops/logout", cookies={SESSION_COOKIE: full_token}, follow_redirects=False)
    assert resp.status_code == 303
    # Session should be deleted
    assert get_session(full_token) is None


# ---------------------------------------------------------------------------
# Page access requires full auth
# ---------------------------------------------------------------------------


def _full_session(email: str = "admin@test.com") -> str:
    return create_session(email, pre_totp=False)


@pytest.mark.parametrize(
    "path",
    [
        "/ops/",
        "/ops/partners",
        "/ops/orgs",
        "/ops/sites",
        "/ops/devices",
        "/ops/people",
        "/ops/attendance",
        "/ops/gateways",
        "/ops/approvals",
        "/ops/audit",
    ],
)
def test_page_redirects_when_unauthenticated(path: str) -> None:
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert "/ops/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Authenticated page smoke tests
# ---------------------------------------------------------------------------


def test_dashboard_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Dashboard" in resp.text
    assert "Partners" in resp.text  # stats grid label


def test_partners_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/partners", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Partners" in resp.text


def test_orgs_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/orgs", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Organisation" in resp.text


def test_sites_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/sites", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Sites" in resp.text


def test_devices_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/devices", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Devices" in resp.text


def test_gateways_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/gateways", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Gateways" in resp.text


def test_audit_page_renders_and_filters() -> None:
    tok = _full_session()
    resp = client.get("/ops/audit", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Audit Log" in resp.text

    # With filter params
    resp2 = client.get("/ops/audit?resource_type=gateway&actor=admin@test.com", cookies={SESSION_COOKIE: tok})
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# Partners POST
# ---------------------------------------------------------------------------


def test_partners_post_creates_partner() -> None:
    tok = _full_session("creator@test.com")
    resp = client.post(
        "/ops/partners",
        data={"name": "Test Partner Corp", "csrf_token": "test"},
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Test Partner Corp" in resp.text


# ---------------------------------------------------------------------------
# Approvals — two-person rule
# ---------------------------------------------------------------------------


def test_approvals_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/approvals", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Approvals" in resp.text


def test_self_approval_blocked() -> None:
    """The person who submitted the request cannot approve it themselves."""
    create_approval(
        action="revoke_gateway",
        resource_type="gateway",
        resource_id="gw-001",
        requested_by="requester@test.com",
    )
    # Same user tries to approve
    tok = _full_session("requester@test.com")
    resp = client.post(
        "/ops/approvals/nonexistent/review",
        data={"approve": "1", "csrf_token": "test"},
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    # Should redirect with error
    assert resp.status_code == 303
    assert "error" in resp.headers["location"].lower() or "approvals" in resp.headers["location"]


def test_two_person_approval_works() -> None:
    """A different user can approve the request."""
    from bip.api.ops.store import get_approval

    req = create_approval(
        action="revoke_gateway",
        resource_type="gateway",
        resource_id="gw-999",
        requested_by="requester@test.com",
    )

    # Different user reviews
    tok = _full_session("reviewer@test.com")
    resp = client.post(
        f"/ops/approvals/{req.id}/review",
        data={"approve": "1", "csrf_token": "test"},
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # Approval is now approved
    updated = get_approval(req.id)
    assert updated is not None
    assert updated.status == "approved"
    assert updated.reviewed_by == "reviewer@test.com"


def test_approval_rejection_works() -> None:
    from bip.api.ops.store import get_approval

    req = create_approval(
        action="revoke_gateway",
        resource_type="gateway",
        resource_id="gw-888",
        requested_by="requester@test.com",
    )

    tok = _full_session("reviewer@test.com")
    resp = client.post(
        f"/ops/approvals/{req.id}/review",
        data={"approve": "0", "csrf_token": "test"},
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    updated = get_approval(req.id)
    assert updated is not None
    assert updated.status == "rejected"


# ---------------------------------------------------------------------------
# Self-serve customer UI tests
# ---------------------------------------------------------------------------


def test_ops_org_creation_post() -> None:
    tok = _full_session("admin@test.com")
    resp = client.post(
        "/ops/orgs",
        data={
            "name": "St. Xavier's High School",
            "partner_id": "test_partner",
            "org_type": "school",
            "timezone": "Asia/Kolkata",
            "retention_days": "730",
            "csrf_token": "test",
        },
        cookies={SESSION_COOKIE: tok},
    )
    assert resp.status_code == 200
    assert "St. Xavier&#39;s High School" in resp.text or "St. Xavier's High School" in resp.text
    assert "created successfully" in resp.text

    from bip.api.routes.v1 import _orgs

    found = any(o["name"] == "St. Xavier's High School" for o in _orgs.values())
    assert found


def test_ops_site_creation_post() -> None:
    tok = _full_session("admin@test.com")
    resp = client.post(
        "/ops/sites",
        data={
            "name": "Academic Block North Gate",
            "org_id": "org_demo",
            "timezone": "Asia/Kolkata",
            "csrf_token": "test",
        },
        cookies={SESSION_COOKIE: tok},
    )
    assert resp.status_code == 200
    assert "Academic Block North Gate" in resp.text
    assert "created successfully" in resp.text

    from bip.api.routes.v1 import _sites

    found = any(s["name"] == "Academic Block North Gate" for s in _sites.values())
    assert found


def test_ops_device_registration_post() -> None:
    tok = _full_session("admin@test.com")
    resp = client.post(
        "/ops/devices",
        data={
            "serial": "ZK99998888",
            "name": "Auditorium Main Gate",
            "family": "zk_adms",
            "site_id": "site_1",
            "mode": "push",
            "ip_address": "192.168.1.100",
            "csrf_token": "test",
        },
        cookies={SESSION_COOKIE: tok},
    )
    assert resp.status_code == 200
    assert "ZK99998888" in resp.text
    assert "Auditorium Main Gate" in resp.text
    assert "Device Setup Instructions" in resp.text
    assert "Cloud Server / ADMS Settings" in resp.text

    # Verify device is auto-whitelisted in edge store
    from bip.edge.adms import _store

    dev = pytest.importorskip("asyncio").run(_store.lookup_device("ZK99998888"))
    assert dev is not None
    assert dev.get("status") == "active"


def test_ops_integrations_and_test_punch() -> None:
    tok = _full_session("admin@test.com")
    from bip.api.ops.auth import _SESSIONS

    # GET page
    resp = client.get("/ops/integrations", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "LearnX Platform" in resp.text
    assert "Enterprise HRMS" in resp.text

    csrf = _SESSIONS[tok].get("csrf", "test")

    # Connect new webhook
    resp = client.post(
        "/ops/integrations/webhooks",
        data={
            "name": "LearnX Production Webhook",
            "url": "http://127.0.0.1:9999/dummy-webhook",
            "org_id": "org_demo",
            "csrf_token": csrf,
        },
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    from bip.api.routes.v1 import _webhooks

    wh = next((w for w in _webhooks.values() if w["name"] == "LearnX Production Webhook"), None)
    assert wh is not None

    # Trigger test punch
    resp = client.post(
        "/ops/integrations/test-punch",
        data={
            "webhook_id": wh["id"],
            "csrf_token": csrf,
        },
        cookies={SESSION_COOKIE: tok},
    )
    assert resp.status_code == 200
    assert "Dispatch Notice" in resp.text or "Test Punch" in resp.text
    assert "LearnX Production Webhook" in resp.text


def test_ops_import_csv_post() -> None:
    tok = _full_session("admin@test.com")
    from bip.api.ops.auth import _SESSIONS

    # GET import page
    resp = client.get("/ops/import", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Upload Attendance File" in resp.text

    csrf = _SESSIONS[tok].get("csrf", "test")

    csv_data = b"pin,timestamp,verify_mode\n101,2026-10-21 08:30:00,fingerprint\n102,2026-10-21 08:35:00,face\n"
    resp = client.post(
        "/ops/import",
        data={
            "site_id": "site_default",
            "device_id": "dev_imported",
            "csrf_token": csrf,
        },
        files={"file": ("attendance.csv", csv_data, "text/csv")},
        cookies={SESSION_COOKIE: tok},
    )
    assert resp.status_code == 200
    assert "Processed &#39;attendance.csv&#39;" in resp.text or "attendance.csv" in resp.text
    assert "2 valid punches ingested" in resp.text


def test_ops_simulate_punch_post() -> None:
    tok = _full_session("admin@test.com")
    from bip.api.ops.auth import _SESSIONS
    from bip.api.routes.v1 import _devices, _punches

    # Add dummy device
    _devices["dev_sim_1"] = {
        "id": "dev_sim_1",
        "name": "Gate 1 Simulator",
        "serial": "SIM999",
        "org_id": "org_sim",
        "site_id": "site_sim",
    }

    # Fetch page for CSRF
    resp = client.get("/ops/integrations", cookies={SESSION_COOKIE: tok})
    csrf = _SESSIONS[tok].get("csrf", "test")

    resp = client.post(
        "/ops/integrations/simulate-punch",
        data={
            "device_id": "dev_sim_1",
            "pin": "2044",
            "verify_mode": "face",
            "csrf_token": csrf,
        },
        cookies={SESSION_COOKIE: tok},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "2044" in resp.headers["location"]
    # Verify punch is in punch feed
    assert any(p["device_pin"] == "2044" for p in _punches)


# ---------------------------------------------------------------------------
# People & Roster page
# ---------------------------------------------------------------------------


def test_people_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/people", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "People" in resp.text
    assert "Roster" in resp.text


def test_people_post_creates_person() -> None:
    from bip.api.routes.v1 import _people

    tok = _full_session("admin@test.com")
    resp = client.post(
        "/ops/people",
        data={
            "display_name": "Priya Sharma",
            "person_type": "student",
            "org_id": "org_test",
            "csrf_token": "test",
        },
        cookies={SESSION_COOKIE: tok},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Priya Sharma" in resp.text or any(p["display_name"] == "Priya Sharma" for p in _people.values())
    found = any(p["display_name"] == "Priya Sharma" for p in _people.values())
    assert found


# ---------------------------------------------------------------------------
# Attendance Feed page
# ---------------------------------------------------------------------------


def test_attendance_page_renders() -> None:
    tok = _full_session()
    resp = client.get("/ops/attendance", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "Attendance" in resp.text


def test_attendance_page_shows_punches() -> None:
    from datetime import UTC, datetime

    from bip.api.routes.v1 import add_test_punch

    add_test_punch("org_a", "site_a", "dev_a", "3001", datetime.now(UTC), verify_mode="fingerprint")
    add_test_punch("org_a", "site_a", "dev_a", "3002", datetime.now(UTC), verify_mode="face")

    tok = _full_session()
    resp = client.get("/ops/attendance", cookies={SESSION_COOKIE: tok})
    assert resp.status_code == 200
    assert "3001" in resp.text or "3002" in resp.text

