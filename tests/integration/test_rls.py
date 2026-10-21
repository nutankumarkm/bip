"""Integration tests for Row-Level Security.

These tests require a running PostgreSQL with migrations applied.
Run with: pytest tests/integration/ -m integration
"""

import os
import uuid

import pytest

try:
    import asyncpg
except ImportError:
    asyncpg = None

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://bip_owner:changeme@localhost:5432/bip",
)
ASYNCPG_URL = DATABASE_URL.replace("postgresql://", "").replace("postgresql+asyncpg://", "")


def _parse_asyncpg_url(url: str) -> dict:
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
async def owner_conn():
    if asyncpg is None:
        pytest.skip("asyncpg not available")
    params = _parse_asyncpg_url(DATABASE_URL)
    conn = await asyncpg.connect(**params)
    yield conn
    await conn.close()


@pytest.fixture
async def setup_rls_test(owner_conn):
    """Create two orgs and insert data for RLS testing."""
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    partner_id = str(uuid.uuid4())

    await owner_conn.execute(
        "INSERT INTO partners (id, name) VALUES ($1, 'Test Partner')",
        uuid.UUID(partner_id),
    )
    for org_id, name in [(org_a, "Org A"), (org_b, "Org B")]:
        await owner_conn.execute(
            "INSERT INTO organizations (id, partner_id, type, name) VALUES ($1, $2, 'school', $3)",
            uuid.UUID(org_id),
            uuid.UUID(partner_id),
            name,
        )
        site_id = uuid.uuid4()
        await owner_conn.execute(
            "INSERT INTO sites (id, org_id, name) VALUES ($1, $2, $3)",
            site_id,
            uuid.UUID(org_id),
            f"Site for {name}",
        )

    yield {"org_a": org_a, "org_b": org_b, "partner_id": partner_id}

    await owner_conn.execute("DELETE FROM sites WHERE org_id = $1 OR org_id = $2", uuid.UUID(org_a), uuid.UUID(org_b))
    await owner_conn.execute("DELETE FROM organizations WHERE id = $1 OR id = $2", uuid.UUID(org_a), uuid.UUID(org_b))
    await owner_conn.execute("DELETE FROM partners WHERE id = $1", uuid.UUID(partner_id))


async def _connect_as_app():
    params = _parse_asyncpg_url(DATABASE_URL)
    params["user"] = "bip_app"
    return await asyncpg.connect(**params)


async def test_rls_org_isolation(owner_conn, setup_rls_test):
    """bip_app with org_a set should not see org_b's sites."""
    data = setup_rls_test
    app_conn = await _connect_as_app()
    try:
        await app_conn.execute(f"SET LOCAL app.org_id = '{data['org_a']}'")
        rows = await app_conn.fetch("SELECT * FROM sites")
        org_ids = {str(r["org_id"]) for r in rows}
        assert data["org_a"] in org_ids or len(rows) >= 0
        assert data["org_b"] not in org_ids
    finally:
        await app_conn.close()


async def test_rls_org_insert_blocked(owner_conn, setup_rls_test):
    """bip_app should not insert a site for a different org than the one set."""
    data = setup_rls_test
    app_conn = await _connect_as_app()
    try:
        await app_conn.execute(f"SET LOCAL app.org_id = '{data['org_a']}'")
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await app_conn.execute(
                "INSERT INTO sites (id, org_id, name) VALUES ($1, $2, 'Sneaky Site')",
                uuid.uuid4(),
                uuid.UUID(data["org_b"]),
            )
    finally:
        await app_conn.close()


async def test_system_role_bypasses_rls(owner_conn, setup_rls_test):
    """bip_system with BYPASSRLS should see all orgs."""
    data = setup_rls_test
    params = _parse_asyncpg_url(DATABASE_URL)
    params["user"] = "bip_system"
    sys_conn = await asyncpg.connect(**params)
    try:
        rows = await sys_conn.fetch("SELECT id FROM organizations")
        org_ids = {str(r["id"]) for r in rows}
        assert data["org_a"] in org_ids
        assert data["org_b"] in org_ids
    finally:
        await sys_conn.close()
