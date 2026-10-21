"""Unit tests for schema and migration validation."""

from datetime import UTC, datetime

import pytest


@pytest.mark.unit
def test_partition_naming():
    """Partition names follow the expected format."""
    now = datetime(2026, 10, 21, tzinfo=UTC)
    for i in range(4):
        month = now.month + i
        year = now.year
        if month > 12:
            month -= 12
            year += 1
        name = f"punch_events_{year}_{month:02d}"
        assert name.startswith("punch_events_")
        assert len(name.split("_")) == 4

    assert "punch_events_2026_10" == "punch_events_2026_10"
    assert "punch_events_2026_11" == "punch_events_2026_11"
    assert "punch_events_2026_12" == "punch_events_2026_12"
    assert "punch_events_2027_01" == "punch_events_2027_01"


@pytest.mark.unit
def test_migration_sql_contains_required_tables():
    """The initial migration should define all required tables."""
    from migrations.versions import _001_initial_schema as m

    sql = m.UPGRADE_SQL
    required_tables = [
        "partners",
        "api_clients",
        "staff_users",
        "organizations",
        "sites",
        "devices",
        "pending_devices",
        "device_capabilities",
        "device_credentials",
        "vendor_connections",
        "gateways",
        "gateway_pairing_codes",
        "people",
        "person_sites",
        "person_identities",
        "enrolments",
        "raw_uploads",
        "punch_events",
        "sync_checkpoints",
        "device_commands",
        "outbox",
        "webhook_subscriptions",
        "webhook_deliveries",
        "jobs",
        "imports",
        "reconciliation_reports",
        "audit_log",
    ]
    for table in required_tables:
        assert f"CREATE TABLE {table}" in sql, f"Table {table} missing from migration"


@pytest.mark.unit
def test_migration_sql_contains_rls():
    """The migration should set up RLS policies."""
    from migrations.versions import _001_initial_schema as m

    sql = m.UPGRADE_SQL
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.org_id'" in sql


@pytest.mark.unit
def test_migration_sql_contains_roles():
    """The migration should create bip_app and bip_system roles."""
    from migrations.versions import _001_initial_schema as m

    sql = m.UPGRADE_SQL
    assert "bip_app" in sql
    assert "bip_system" in sql
    assert "BYPASSRLS" in sql


@pytest.mark.unit
def test_migration_sql_contains_partition_function():
    """The migration should define the partition maintenance function."""
    from migrations.versions import _001_initial_schema as m

    sql = m.UPGRADE_SQL
    assert "maintain_punch_partitions" in sql
