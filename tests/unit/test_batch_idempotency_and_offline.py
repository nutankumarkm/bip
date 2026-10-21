"""Tests for Batch punch upload idempotency and simulated 72h offline period (M6 Acceptance Gate)."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.routes.gateway import _gateways, reset_gateway_stores
from bip.api.routes.v1 import _punches, reset_stores
from bip.gateway.keys import generate_keypair, public_key_to_b64, sign_request
from bip.gateway.outbox import LocalOutbox
from bip.gateway.uploader import OutboxUploader

client = TestClient(app)

ORG_ID = "00000000-0000-0000-0000-000000000002"
SITE_ID = "00000000-0000-0000-0000-000000000003"


def setup_function() -> None:
    reset_gateway_stores()
    reset_stores()


def test_batch_punch_upload_idempotency() -> None:
    """Replaying a batch with the same batch_id is completely idempotent."""
    priv, pub = generate_keypair()
    gw_id = "gw-idempotency-test"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": ORG_ID,
        "site_id": SITE_ID,
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    batch_id = str(uuid.uuid4())
    punches = [
        {
            "device_pin": f"PIN-{i}",
            "device_local_time": (datetime.now(UTC) - timedelta(minutes=i)).isoformat(),
            "verify_mode": "fingerprint",
        }
        for i in range(10)
    ]

    path = "/gw/v1/punches:batch"
    body = {
        "batch_id": batch_id,
        "device_id": "ZK-IDEM-01",
        "events": punches,
    }
    body_bytes = json.dumps(body).encode()

    # 1. First upload
    now_ts = int(time.time())
    sig = sign_request(priv, "POST", path, body_bytes, now_ts)
    headers = {
        "Content-Type": "application/json",
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts),
        "X-BIP-Signature": sig,
    }

    resp1 = client.post(path, content=body_bytes, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["accepted"] == 10
    assert resp1.json()["batch_id"] == batch_id
    assert len(_punches) == 10

    # 2. Replay the exact same batch with same batch_id (simulating network retry)
    now_ts2 = int(time.time())
    sig2 = sign_request(priv, "POST", path, body_bytes, now_ts2)
    headers2 = {
        "Content-Type": "application/json",
        "X-BIP-Gateway": gw_id,
        "X-BIP-Timestamp": str(now_ts2),
        "X-BIP-Signature": sig2,
    }

    resp2 = client.post(path, content=body_bytes, headers=headers2)
    assert resp2.status_code == 200
    assert resp2.json()["accepted"] == 10
    assert resp2.json()["batch_id"] == batch_id

    # Crucial check: punch count in system must NOT have doubled!
    assert len(_punches) == 10, f"Expected 10 punches after replayed batch, found {len(_punches)}"


@pytest.mark.asyncio
async def test_simulated_72h_offline_period_no_loss(tmp_path: Path) -> None:
    """A simulated 72-hour offline period: all punches accumulate safely in outbox,

    and when connectivity is restored, all 1,200 punches are uploaded with zero loss.
    """
    priv, pub = generate_keypair()
    gw_id = "gw-offline-72h-test"
    _gateways[gw_id] = {
        "id": gw_id,
        "org_id": ORG_ID,
        "site_id": SITE_ID,
        "status": "active",
        "public_key": public_key_to_b64(pub),
    }

    # 1. Initialize local outbox
    db_path = tmp_path / "offline_gateway.sqlite3"
    outbox = LocalOutbox(db_path)

    # 2. Simulate 72 hours of offline operation across 2 devices
    # 72 hours = 3 days; morning, noon, evening punches
    start_time = datetime.now(UTC) - timedelta(hours=72)
    total_generated = 1200
    device_serials = ["ZK-DOOR-NORTH", "ZK-DOOR-SOUTH"]

    # Generate punches in chunks of 50 (e.g. burst arrivals at terminal)
    chunk_size = 50
    punches_accumulator: list[dict] = []

    for i in range(total_generated):
        # Progressively space punches across the 72 hour window
        offset_minutes = int((i / total_generated) * (72 * 60))
        punch_time = start_time + timedelta(minutes=offset_minutes)
        serial = device_serials[i % 2]

        punches_accumulator.append(
            {
                "device_pin": f"USER{1000 + (i % 200)}",
                "device_local_time": punch_time.isoformat(),
                "verify_mode": "fingerprint" if i % 3 != 0 else "card",
            }
        )

        if len(punches_accumulator) == chunk_size:
            outbox.enqueue(serial, punches_accumulator)
            punches_accumulator = []

    if punches_accumulator:
        outbox.enqueue(device_serials[0], punches_accumulator)

    # Verify all 1,200 punches are stored durably in the local outbox across 24 batch rows
    expected_rows = total_generated // chunk_size
    assert outbox.pending_count() == expected_rows
    assert outbox.total_count() == expected_rows

    # 3. Network restored: connect Uploader with httpx ASGITransport
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        uploader = OutboxUploader(
            outbox=outbox,
            cloud_url="http://testserver",
            gateway_id=gw_id,
            private_key=priv,
            batch_size=200,  # Upload in batches of 200
            client=async_client,
        )

        # Upload all pending punches across multiple batches
        total_uploaded = 0
        while outbox.pending_count() > 0:
            uploaded = await uploader.upload_pending(client=async_client)
            assert uploaded > 0
            total_uploaded += uploaded

    # 4. Acceptance verification
    assert total_uploaded == total_generated, f"Expected {total_generated} uploaded, got {total_uploaded}"
    assert outbox.pending_count() == 0, "Outbox pending count must be 0 after full sync"
    assert len(_punches) == total_generated, f"Server must hold all {total_generated} punches, found {len(_punches)}"

    # 5. Verify local outbox purge
    purged = outbox.purge_uploaded(older_than_hours=0)
    assert purged > 0
    assert outbox.total_count() == 0

    outbox.close()
