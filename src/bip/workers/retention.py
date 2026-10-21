"""Retention purge worker — deletes punch events older than org.retention_days (M9)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from bip.core.logging import get_logger

log = get_logger(__name__)

DEFAULT_RETENTION_DAYS = 730  # 2 years per spec


def purge_expired_punches(
    retention_days: int | None = None,
    org_id: str | None = None,
    batch_size: int = 1000,
    db_session: Any = None,
) -> int:
    """Purge punches older than the specified or org-configured retention_days.

    Operates in memory when in test mode, or via SQL session when available.
    Returns the total count of purged punches.
    """
    total_purged = 0
    now = datetime.now(UTC)

    # 1. Check in-memory store (primary test path)
    try:
        from bip.api.routes.v1 import _orgs, _punches

        # Determine cutoff per org or global
        if org_id:
            org = _orgs.get(org_id, {})
            days = retention_days if retention_days is not None else org.get("retention_days", DEFAULT_RETENTION_DAYS)
            cutoff = now - timedelta(days=days)

            # Filter out expired punches for this org
            before_count = len(_punches)
            _punches[:] = [
                p for p in _punches if not (p.get("org_id") == org_id and _parse_ts(p.get("punch_time", now)) < cutoff)
            ]
            total_purged += before_count - len(_punches)
        else:
            # Purge across all orgs using their respective retention_days
            before_count = len(_punches)
            surviving = []
            for p in _punches:
                p_org_id = p.get("org_id", "")
                p_org = _orgs.get(p_org_id, {})
                days = (
                    retention_days
                    if retention_days is not None
                    else p_org.get("retention_days", DEFAULT_RETENTION_DAYS)
                )
                cutoff = now - timedelta(days=days)
                p_time = _parse_ts(p.get("punch_time", now))
                if p_time >= cutoff:
                    surviving.append(p)
            _punches[:] = surviving
            total_purged += before_count - len(_punches)

    except ImportError:
        pass

    # 2. Database session purge if provided
    if db_session is not None:
        try:
            from sqlalchemy import text

            cutoff = now - timedelta(days=retention_days or DEFAULT_RETENTION_DAYS)
            if org_id:
                stmt = text("DELETE FROM punch_events WHERE org_id = :org_id AND punch_time < :cutoff")
                res = db_session.execute(stmt, {"org_id": org_id, "cutoff": cutoff})
            else:
                stmt = text(
                    "DELETE FROM punch_events USING orgs WHERE punch_events.org_id = orgs.id "
                    "AND punch_events.punch_time < (NOW() - (orgs.retention_days || ' days')::interval)"
                )
                res = db_session.execute(stmt)
            db_session.commit()
            total_purged += res.rowcount if hasattr(res, "rowcount") else 0
        except Exception as exc:
            log.warning("db_retention_purge_failed", error=str(exc))

    log.info("retention_purge_completed", purged_count=total_purged, org_id=org_id)
    return total_purged


def _parse_ts(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


async def run_retention_loop(
    interval_seconds: int = 86400,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Periodic worker loop for purging data past retention window."""
    log.info("retention_worker_started", interval_seconds=interval_seconds)
    while True:
        try:
            purge_expired_punches()
        except Exception as exc:
            log.error("retention_worker_error", error=str(exc))

        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
                break
            except TimeoutError:
                continue
        else:
            await asyncio.sleep(interval_seconds)

    log.info("retention_worker_stopped")
