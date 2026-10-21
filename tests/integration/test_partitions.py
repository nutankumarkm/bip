"""Integration tests for punch_events partitioning.

Requires a running PostgreSQL with migrations applied.
"""

import os
from datetime import UTC, datetime

import pytest

try:
    import asyncpg
except ImportError:
    asyncpg = None

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _parse_asyncpg_url() -> dict:
    sync_url = os.environ.get("DATABASE_URL_SYNC", "postgresql://bip_owner:changeme@localhost:5432/bip")
    from urllib.parse import urlparse

    parsed = urlparse(sync_url)
    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
    }


@pytest.fixture
async def conn():
    if asyncpg is None:
        pytest.skip("asyncpg not available")
    params = _parse_asyncpg_url()
    c = await asyncpg.connect(**params)
    yield c
    await c.close()


async def test_current_month_partition_exists(conn):
    """The partition for the current month should exist after migration."""
    now = datetime.now(UTC)
    part_name = f"punch_events_{now.year}_{now.month:02d}"
    row = await conn.fetchrow("SELECT 1 FROM pg_class WHERE relname = $1", part_name)
    assert row is not None, f"Partition {part_name} should exist"


async def test_default_partition_exists(conn):
    """The default partition should exist."""
    row = await conn.fetchrow("SELECT 1 FROM pg_class WHERE relname = 'punch_events_default'")
    assert row is not None, "Default partition should exist"


async def test_maintain_partitions_function(conn):
    """The maintain_punch_partitions function should be callable."""
    await conn.execute("SELECT maintain_punch_partitions()")


async def test_partition_maintenance_creates_future(conn):
    """After calling maintain_punch_partitions, next 3 months should exist."""
    await conn.execute("SELECT maintain_punch_partitions()")
    now = datetime.now(UTC)
    for i in range(4):
        month = now.month + i
        year = now.year
        if month > 12:
            month -= 12
            year += 1
        part_name = f"punch_events_{year}_{month:02d}"
        row = await conn.fetchrow("SELECT 1 FROM pg_class WHERE relname = $1", part_name)
        assert row is not None, f"Partition {part_name} should exist after maintenance"
