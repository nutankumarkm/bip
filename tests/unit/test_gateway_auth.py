"""Tests for Gateway Ed25519 request signing and authentication (ADR-009, M6)."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.routes.gateway import _gateways, reset_gateway_stores
from bip.gateway.keys import generate_keypair, public_key_to_b64, sign_request

client = TestClient(app)


def setup_function() -> None:
    reset_gateway_stores()


def test_gateway_auth_success() -> None:
    """Valid signed request with active gateway succeeds."""
    priv, pub = generate_keypair()
    gw_id = "gw-test-01"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": "org-test-1",
        "site_id": "site-test-1",
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    path = "/gw/v1/config"
    now_ts = int(time.time())
    sig = sign_request(priv, "GET", path, b"", now_ts)

    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["gateway_id"] == gw_id


def test_gateway_auth_tampered_signature_rejected() -> None:
    """Tampered signature must be rejected with 401."""
    priv, pub = generate_keypair()
    gw_id = "gw-test-tampered"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": "org-test-1",
        "site_id": "site-test-1",
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    path = "/gw/v1/config"
    now_ts = int(time.time())
    sig = sign_request(priv, "GET", path, b"", now_ts)
    # Tamper with the base64 signature
    tampered_sig = ("A" if sig[0] != "A" else "B") + sig[1:]

    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": tampered_sig,
    }

    resp = client.get(path, headers=headers)
    assert resp.status_code == 401
    assert "Invalid request signature" in resp.json()["detail"]


def test_gateway_auth_tampered_body_rejected() -> None:
    """Modifying body after signature must be rejected with 401."""
    priv, pub = generate_keypair()
    gw_id = "gw-test-body"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": "org-test-1",
        "site_id": "site-test-1",
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    path = "/gw/v1/heartbeat"
    now_ts = int(time.time())
    original_body = json.dumps({"version": "0.1.0", "queue_depth": 0}).encode()
    sig = sign_request(priv, "POST", path, original_body, now_ts)

    # Send tampered body with original signature
    tampered_body = json.dumps({"version": "0.1.0", "queue_depth": 999}).encode()
    headers = {
        "Content-Type": "application/json",
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.post(path, content=tampered_body, headers=headers)
    assert resp.status_code == 401
    assert "Invalid request signature" in resp.json()["detail"]


def test_gateway_auth_clock_skew_rejected() -> None:
    """Request with timestamp > 300s in past or future must be rejected with 401."""
    priv, pub = generate_keypair()
    gw_id = "gw-test-skew"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": "org-test-1",
        "site_id": "site-test-1",
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    path = "/gw/v1/config"
    old_ts = int(time.time()) - 350  # 350 seconds ago (> 300s limit)
    sig = sign_request(priv, "GET", path, b"", old_ts)

    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(old_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.get(path, headers=headers)
    assert resp.status_code == 401
    assert "skew exceeds 300 seconds" in resp.json()["detail"]


def test_gateway_auth_revoked_or_inactive_rejected() -> None:
    """Revoked gateway must be rejected with 403 Forbidden."""
    priv, pub = generate_keypair()
    gw_id = "gw-test-revoked"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": "org-test-1",
        "site_id": "site-test-1",
        "status": "revoked",
        "public_key": public_key_to_b64(pub),
    }

    path = "/gw/v1/config"
    now_ts = int(time.time())
    sig = sign_request(priv, "GET", path, b"", now_ts)

    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.get(path, headers=headers)
    assert resp.status_code == 403
    assert "not active" in resp.json()["detail"]


def test_gateway_auth_unknown_gateway_rejected() -> None:
    """Unknown gateway ID must be rejected with 401."""
    priv, _ = generate_keypair()
    gw_id = "gw-unknown-999"

    path = "/gw/v1/config"
    now_ts = int(time.time())
    sig = sign_request(priv, "GET", path, b"", now_ts)

    headers = {
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp = client.get(path, headers=headers)
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()
