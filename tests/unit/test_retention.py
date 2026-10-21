"""Unit tests for punch data retention purge worker (M9)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from bip.api.routes.v1 import _orgs, _punches
from bip.workers.retention import purge_expired_punches, run_retention_loop


def test_purge_expired_punches_by_org_retention() -> None:
    _punches.clear()
    _orgs.clear()

    now = datetime.now(UTC)

    # Org A: 30 days retention
    _orgs["org_a"] = {"id": "org_a", "name": "Org A", "retention_days": 30}
    # Org B: 365 days retention
    _orgs["org_b"] = {"id": "org_b", "name": "Org B", "retention_days": 365}

    # Punches for Org A
    # 1. Recent (10 days old) -> Keep
    _punches.append({"id": "p1", "org_id": "org_a", "punch_time": now - timedelta(days=10)})
    # 2. Expired (45 days old) -> Purge
    _punches.append({"id": "p2", "org_id": "org_a", "punch_time": now - timedelta(days=45)})

    # Punches for Org B
    # 3. 45 days old -> Keep (Org B has 365 days retention)
    _punches.append({"id": "p3", "org_id": "org_b", "punch_time": now - timedelta(days=45)})
    # 4. 400 days old -> Purge
    _punches.append({"id": "p4", "org_id": "org_b", "punch_time": now - timedelta(days=400)})

    # Purge all orgs
    purged = purge_expired_punches()
    assert purged == 2

    # Verify surviving punches
    surviving_ids = [p["id"] for p in _punches]
    assert "p1" in surviving_ids
    assert "p3" in surviving_ids
    assert "p2" not in surviving_ids
    assert "p4" not in surviving_ids


def test_purge_specific_org_only() -> None:
    _punches.clear()
    _orgs.clear()

    now = datetime.now(UTC)
    _orgs["org_x"] = {"id": "org_x", "retention_days": 7}
    _orgs["org_y"] = {"id": "org_y", "retention_days": 7}

    _punches.append({"id": "px_old", "org_id": "org_x", "punch_time": now - timedelta(days=14)})
    _punches.append({"id": "py_old", "org_id": "org_y", "punch_time": now - timedelta(days=14)})

    # Purge ONLY org_x
    purged = purge_expired_punches(org_id="org_x")
    assert purged == 1

    surviving_ids = [p["id"] for p in _punches]
    assert "px_old" not in surviving_ids
    assert "py_old" in surviving_ids  # Untouched


def test_purge_with_explicit_retention_days_override() -> None:
    _punches.clear()
    _orgs.clear()

    now = datetime.now(UTC)
    _orgs["org_z"] = {"id": "org_z", "retention_days": 730}

    _punches.append({"id": "pz_1", "org_id": "org_z", "punch_time": now - timedelta(days=5)})
    _punches.append({"id": "pz_2", "org_id": "org_z", "punch_time": now - timedelta(days=20)})

    # Override retention_days=10
    purged = purge_expired_punches(retention_days=10)
    assert purged == 1
    assert len(_punches) == 1
    assert _punches[0]["id"] == "pz_1"


async def test_run_retention_loop_stops_on_event() -> None:
    stop_event = asyncio.Event()

    async def _stopper() -> None:
        await asyncio.sleep(0.05)
        stop_event.set()

    stopper_task = asyncio.create_task(_stopper())
    await run_retention_loop(interval_seconds=10, stop_event=stop_event)
    await stopper_task
