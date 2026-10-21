"""Tests for Gateway local feed API, network discovery, and updater (section 11, M6)."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bip.gateway.discovery import NetworkDiscovery
from bip.gateway.keys import generate_keypair
from bip.gateway.local_feed import create_local_feed_app
from bip.gateway.outbox import LocalOutbox
from bip.gateway.updater import (
    AgentUpdater,
    build_manifest_canonical_bytes,
    verify_manifest_signature,
)


def test_local_feed_auth_and_cursor_pagination(tmp_path: Path) -> None:
    """Test gateway local feed serves punches from outbox with token auth and pagination."""
    db_path = tmp_path / "feed.sqlite3"
    token_path = tmp_path / "token.txt"
    token_path.write_text("secret-learnx-local-token")

    outbox = LocalOutbox(db_path)
    now = datetime.now(UTC).isoformat()

    # Enqueue 15 punches
    punches = [{"device_pin": f"PIN-{i}", "device_local_time": now, "verify_mode": "fingerprint"} for i in range(15)]
    outbox.enqueue("ZK-SERIAL-LOCAL", punches[:10])
    outbox.enqueue("ZK-SERIAL-LOCAL", punches[10:])

    app = create_local_feed_app(outbox, token_path=token_path)
    client = TestClient(app)

    # 1. Unauthenticated request rejected
    resp_unauth = client.get("/v1/punches")
    assert resp_unauth.status_code == 401

    # 2. Bad token rejected
    resp_bad = client.get("/v1/punches", headers={"Authorization": "Bearer wrong-token"})
    assert resp_bad.status_code == 403

    # 3. Valid token accepted, page 1
    resp_page1 = client.get(
        "/v1/punches?limit=10",
        headers={"Authorization": "Bearer secret-learnx-local-token"},
    )
    assert resp_page1.status_code == 200
    data1 = resp_page1.json()
    assert len(data1["items"]) == 10
    assert data1["next_cursor"] is not None

    # 4. Page 2 using next_cursor
    cursor = data1["next_cursor"]
    resp_page2 = client.get(
        f"/v1/punches?cursor={cursor}&limit=10",
        headers={"Authorization": "Bearer secret-learnx-local-token"},
    )
    assert resp_page2.status_code == 200
    data2 = resp_page2.json()
    assert len(data2["items"]) == 5

    outbox.close()


@pytest.mark.asyncio
async def test_network_discovery_scanner() -> None:
    """Network discovery scanner checks ports and identifies devices."""
    discovery = NetworkDiscovery(ports=[4370, 80], timeout=0.1)

    # Scanning non-existent or localhost closed port should not crash
    results = await discovery.scan_cidr("127.0.0.1/32", max_hosts=1)
    assert isinstance(results, list)


def test_agent_updater_verification_and_swap_rollback(tmp_path: Path) -> None:
    """Test updater signature verification, file hash checks, staging, swap, and rollback."""
    priv, pub = generate_keypair()

    version = "0.2.0"
    url = "https://updates.bip.local/agent-0.2.0.tar.gz"
    content = b"Simulated binary update payload v0.2.0"
    content_hash = hashlib.sha256(content).hexdigest()

    # 1. Valid signature
    message = build_manifest_canonical_bytes(version, url, content_hash)
    sig_b64 = base64.b64encode(priv.sign(message)).decode("ascii")

    manifest = {
        "version": version,
        "url": url,
        "sha256": content_hash,
        "signature": sig_b64,
    }
    assert verify_manifest_signature(manifest, pub) is True

    # 2. Tampered signature fails
    tampered_sig = ("A" if sig_b64[0] != "A" else "B") + sig_b64[1:]
    bad_manifest = {**manifest, "signature": tampered_sig}
    assert verify_manifest_signature(bad_manifest, pub) is False

    # 3. File hash verification
    test_file = tmp_path / "downloaded.bin"
    test_file.write_bytes(content)

    stage_dir = tmp_path / "stage"
    current_dir = tmp_path / "current"
    backup_dir = tmp_path / "backup"

    # Setup initial current directory
    current_dir.mkdir(parents=True, exist_ok=True)
    (current_dir / "app.bin").write_text("v0.1.0")

    updater = AgentUpdater(
        cloud_url="http://localhost:8080",
        pinned_public_key=pub,
        stage_dir=stage_dir,
        current_dir=current_dir,
        backup_dir=backup_dir,
    )

    assert updater.verify_file_hash(test_file, content_hash) is True
    assert updater.verify_file_hash(test_file, "wrong-hash") is False

    # 4. Stage and swap
    updater.stage_file(test_file, "app.bin")
    success = updater.swap_and_backup()
    assert success is True
    assert (current_dir / "app.bin").read_bytes() == content
    assert (backup_dir / "app.bin").read_text() == "v0.1.0"

    # 5. Rollback on simulated health check failure
    rollback_ok = updater.rollback()
    assert rollback_ok is True
    assert (current_dir / "app.bin").read_text() == "v0.1.0"
