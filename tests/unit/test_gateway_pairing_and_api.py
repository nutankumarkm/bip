"""Tests for Gateway pairing lifecycle, consumer endpoints, and gateway API services (M6)."""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.auth import clear_orgs, create_access_token, register_org
from bip.api.routes.gateway import (
    _gateways,
    _pairing_codes,
    _release_pub_key,
    reset_gateway_stores,
)
from bip.api.routes.v1 import _commands, _devices, reset_stores
from bip.gateway.keys import generate_keypair, public_key_to_b64, sign_request
from bip.gateway.updater import verify_manifest_signature

client = TestClient(app)

PARTNER_ID = "00000000-0000-0000-0000-000000000001"
ORG_ID = "00000000-0000-0000-0000-000000000002"
SITE_ID = "00000000-0000-0000-0000-000000000003"


def _auth_headers(scopes: list[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        {
            "client_id": "test-client-1",
            "partner_id": PARTNER_ID,
            "scopes": scopes or ["gateways:write", "devices:read", "devices:write"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    reset_gateway_stores()
    reset_stores()
    clear_orgs()
    register_org(ORG_ID, PARTNER_ID)


def test_gateway_registration_and_pairing_lifecycle() -> None:
    """Register gateway via consumer API, pair via agent API, verify activation."""
    headers = _auth_headers()

    # 1. Register gateway (consumer API)
    resp = client.post(
        f"/v1/orgs/{ORG_ID}/gateways",
        json={"site_id": SITE_ID, "name": "School Main Office Gateway"},
        headers=headers,
    )
    assert resp.status_code == 201
    gw_data = resp.json()
    gw_id = gw_data["id"]
    code = gw_data["pairing_code"]

    # Must be 8 numeric digits per spec
    assert re.match(r"^\d{8}$", code), f"Expected 8-digit numeric pairing code, got {code}"
    assert gw_data["status"] == "pairing"

    # 2. Pair gateway (Agent API)
    _priv, pub = generate_keypair()
    pub_b64 = public_key_to_b64(pub)

    pair_resp = client.post(
        "/gw/v1/pair",
        json={"code": code, "public_key": pub_b64, "hostname": "school-gw-01", "version": "0.1.0"},
    )
    assert pair_resp.status_code == 200
    pair_data = pair_resp.json()
    assert pair_data["gateway_id"] == gw_id
    assert "config" in pair_data

    # Verify status changed to active
    gw = _gateways[gw_id]
    assert gw["status"] == "active"
    assert gw["public_key"] == pub_b64

    # 3. Re-using pairing code must fail
    fail_resp = client.post(
        "/gw/v1/pair",
        json={"code": code, "public_key": pub_b64},
    )
    assert fail_resp.status_code == 401


def test_gateway_pairing_expired_code_rejected() -> None:
    """Expired pairing code must be rejected with 401."""
    headers = _auth_headers()
    resp = client.post(
        f"/v1/orgs/{ORG_ID}/gateways",
        json={"site_id": SITE_ID, "name": "Test Gateway"},
        headers=headers,
    )
    code = resp.json()["pairing_code"]

    # Artificially expire the pairing code
    for pc in _pairing_codes.values():
        pc["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()

    _, pub = generate_keypair()
    fail_resp = client.post(
        "/gw/v1/pair",
        json={"code": code, "public_key": public_key_to_b64(pub)},
    )
    assert fail_resp.status_code == 401


def test_gateway_consumer_list_and_revoke() -> None:
    """Test consumer listing, get, and revocation of gateways."""
    headers = _auth_headers()
    reg_resp = client.post(
        f"/v1/orgs/{ORG_ID}/gateways",
        json={"site_id": SITE_ID, "name": "Lab Gateway"},
        headers=headers,
    )
    gw_id = reg_resp.json()["id"]

    # List
    list_resp = client.get(f"/v1/orgs/{ORG_ID}/gateways", headers=headers)
    assert list_resp.status_code == 200
    assert any(g["id"] == gw_id for g in list_resp.json())

    # Get
    get_resp = client.get(f"/v1/orgs/{ORG_ID}/gateways/{gw_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == gw_id

    # Revoke
    del_resp = client.delete(f"/v1/orgs/{ORG_ID}/gateways/{gw_id}", headers=headers)
    assert del_resp.status_code == 200
    assert _gateways[gw_id]["status"] == "revoked"


def test_gateway_heartbeat_updates_device_metrics() -> None:
    """Heartbeat endpoint updates gateway state and assigned device metrics."""
    priv, pub = generate_keypair()
    gw_id = "gw-heartbeat-test"
    dev_id = "dev-hb-1"

    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": ORG_ID,
        "site_id": SITE_ID,
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    _devices[dev_id] = {
        "id": dev_id,
        "org_id": ORG_ID,
        "site_id": SITE_ID,
        "serial": "ZK-HB-01",
        "status": "expected",
        "gateway_id": gw_id,
    }

    path = "/gw/v1/heartbeat"
    now_ts = int(time.time())
    body = {
        "version": "0.1.2",
        "queue_depth": 42,
        "disk_free_mb": 512.5,
        "devices": [
            {
                "device_id": dev_id,
                "reachable": True,
                "drift_s": 3,
                "log_fill_pct": 25,
            }
        ],
    }
    body_bytes = json.dumps(body).encode()
    sig = sign_request(priv, "POST", path, body_bytes, now_ts)

    headers = {
        "Content-Type": "application/json",
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.post(path, content=body_bytes, headers=headers)
    assert resp.status_code == 200

    gw = _gateways[gw_id]
    assert gw["version"] == "0.1.2"
    assert gw["queue_depth"] == 42
    assert gw["disk_free_mb"] == 512.5

    dev = _devices[dev_id]
    assert dev["status"] == "active"
    assert dev["clock_drift_s"] == 3
    assert dev["log_fill_pct"] == 25


def test_gateway_commands_polling_and_result() -> None:
    """Test long-polling commands and posting execution result."""
    priv, pub = generate_keypair()
    gw_id = "gw-cmd-test"
    dev_id = "dev-cmd-1"

    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": ORG_ID,
        "site_id": SITE_ID,
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    cmd_id = "cmd-12345"
    _commands[cmd_id] = {
        "id": cmd_id,
        "org_id": ORG_ID,
        "device_id": dev_id,
        "type": "set_user",
        "params": {"pin": "5001", "name": "Priya Sharma"},
        "state": "queued",
    }

    # Poll commands with wait=0
    path = "/gw/v1/commands?wait=0"
    now_ts = int(time.time())
    sig = sign_request(priv, "GET", path, b"", now_ts)
    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    poll_resp = client.get(path, headers=headers)
    assert poll_resp.status_code == 200
    cmds = poll_resp.json()["commands"]
    assert len(cmds) == 1
    assert cmds[0]["id"] == cmd_id
    assert _commands[cmd_id]["state"] == "sent"

    # Post command result
    res_path = f"/gw/v1/commands/{cmd_id}/result"
    res_body = {
        "command_id": cmd_id,
        "success": True,
        "return_code": 0,
        "message": "User set successfully",
    }
    res_bytes = json.dumps(res_body).encode()
    now_ts = int(time.time())
    res_sig = sign_request(priv, "POST", res_path, res_bytes, now_ts)
    res_headers = {
        "Content-Type": "application/json",
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": res_sig,
    }

    post_resp = client.post(res_path, content=res_bytes, headers=res_headers)
    assert post_resp.status_code == 200
    assert _commands[cmd_id]["state"] == "succeeded"


def test_gateway_release_manifest_signature_verification() -> None:
    """Release manifest endpoint returns valid Ed25519 signature."""
    resp = client.get("/gw/v1/release")
    assert resp.status_code == 200
    manifest = resp.json()
    assert manifest["version"] == "0.2.0"
    assert "signature" in manifest

    # Must verify against master release public key
    assert verify_manifest_signature(manifest, _release_pub_key)
