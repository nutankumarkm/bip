"""Initial schema — all tables, roles, RLS, partitions.

Revision ID: 001
Revises: None
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_SQL = """
-- ===========================================================================
-- Database roles
-- ===========================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bip_app') THEN
        CREATE ROLE bip_app LOGIN PASSWORD 'changeme';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bip_system') THEN
        CREATE ROLE bip_system LOGIN PASSWORD 'changeme' BYPASSRLS;
    END IF;
END
$$;

-- ===========================================================================
-- Extensions
-- ===========================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ===========================================================================
-- Partners and API clients
-- ===========================================================================
CREATE TABLE partners (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_clients (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    partner_id uuid NOT NULL REFERENCES partners(id),
    name text NOT NULL,
    client_id text NOT NULL UNIQUE,
    secret_hash text NOT NULL,
    scopes text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Staff users (ops console)
-- ===========================================================================
CREATE TABLE staff_users (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    totp_secret_enc bytea,
    role text NOT NULL CHECK (role IN ('platform_admin', 'support', 'viewer')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Organizations and sites
-- ===========================================================================
CREATE TABLE organizations (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    partner_id uuid NOT NULL REFERENCES partners(id),
    type text NOT NULL CHECK (type IN ('school', 'college', 'company')),
    name text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Kolkata',
    retention_days int NOT NULL DEFAULT 730,
    pin_range_start int NOT NULL DEFAULT 10001,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sites (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    name text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Kolkata',
    active_hours jsonb,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Devices
-- ===========================================================================
CREATE TABLE devices (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    site_id uuid NOT NULL REFERENCES sites(id),
    vendor text NOT NULL,
    family text NOT NULL CHECK (family IN (
        'zk_adms', 'zk_tcp', 'hik_isapi', 'biotime', 'cosec', 'db_read', 'file'
    )),
    serial text,
    model text,
    firmware text,
    mode text NOT NULL CHECK (mode IN ('push', 'gateway', 'vendor', 'file')),
    status text NOT NULL DEFAULT 'expected' CHECK (status IN ('expected', 'active', 'disabled')),
    gateway_id uuid,
    address text,
    last_seen_at timestamptz,
    clock_drift_s int,
    log_fill_pct smallint,
    push_secret_hash text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_devices_vendor_serial
    ON devices (vendor, serial) WHERE serial IS NOT NULL;

-- ===========================================================================
-- Pending devices (system table, no org)
-- ===========================================================================
CREATE TABLE pending_devices (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    serial text NOT NULL,
    vendor text NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    last_ip text,
    info jsonb,
    UNIQUE (serial, vendor)
);

-- ===========================================================================
-- Device capabilities and credentials
-- ===========================================================================
CREATE TABLE device_capabilities (
    device_id uuid NOT NULL REFERENCES devices(id),
    capability text NOT NULL,
    status text NOT NULL DEFAULT 'declared' CHECK (status IN (
        'declared', 'probed', 'verified', 'unsupported'
    )),
    checked_at timestamptz,
    PRIMARY KEY (device_id, capability)
);

CREATE TABLE device_credentials (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id uuid NOT NULL REFERENCES devices(id),
    kind text NOT NULL,
    ciphertext bytea NOT NULL,
    key_ref text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Vendor connections
-- ===========================================================================
CREATE TABLE vendor_connections (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    site_id uuid NOT NULL REFERENCES sites(id),
    vendor text NOT NULL CHECK (vendor IN ('biotime', 'cosec')),
    base_url text NOT NULL,
    credential_ciphertext bytea NOT NULL,
    key_ref text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    last_sync_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Gateways
-- ===========================================================================
CREATE TABLE gateways (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    site_id uuid NOT NULL REFERENCES sites(id),
    name text NOT NULL,
    public_key bytea,
    status text NOT NULL DEFAULT 'pairing' CHECK (status IN ('pairing', 'active', 'revoked')),
    version text,
    last_seen_at timestamptz,
    queue_depth int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gateway_pairing_codes (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    gateway_id uuid NOT NULL REFERENCES gateways(id),
    code_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Add FK from devices to gateways now that gateways table exists
ALTER TABLE devices ADD CONSTRAINT fk_devices_gateway
    FOREIGN KEY (gateway_id) REFERENCES gateways(id);

-- ===========================================================================
-- People
-- ===========================================================================
CREATE TABLE people (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    external_ref text NOT NULL,
    person_type text NOT NULL CHECK (person_type IN ('student', 'staff', 'employee')),
    display_name text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, external_ref)
);

CREATE TABLE person_sites (
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    site_id uuid NOT NULL REFERENCES sites(id),
    PRIMARY KEY (person_id, site_id)
);

CREATE TABLE person_identities (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    person_id uuid NOT NULL UNIQUE REFERENCES people(id) ON DELETE CASCADE,
    org_id uuid NOT NULL REFERENCES organizations(id),
    device_pin text NOT NULL,
    card_no text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, device_pin)
);

-- ===========================================================================
-- Enrolments
-- ===========================================================================
CREATE TABLE enrolments (
    person_id uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    device_id uuid NOT NULL REFERENCES devices(id),
    fingerprints smallint NOT NULL DEFAULT 0,
    face boolean NOT NULL DEFAULT false,
    palm boolean NOT NULL DEFAULT false,
    card boolean NOT NULL DEFAULT false,
    synced_at timestamptz,
    PRIMARY KEY (person_id, device_id)
);

-- ===========================================================================
-- Raw uploads (Edge durable inbox)
-- ===========================================================================
CREATE TABLE raw_uploads (
    id bigserial PRIMARY KEY,
    device_id uuid,
    serial text,
    family text NOT NULL,
    endpoint text NOT NULL,
    query jsonb,
    body text,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    error text
);

-- ===========================================================================
-- Punch events — partitioned by month
-- ===========================================================================
CREATE SEQUENCE punch_event_seq;

CREATE TABLE punch_events (
    seq bigint NOT NULL DEFAULT nextval('punch_event_seq'),
    id uuid NOT NULL DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL,
    site_id uuid NOT NULL,
    device_id uuid NOT NULL,
    person_id uuid,
    device_pin text NOT NULL,
    device_local_time timestamp NOT NULL,
    device_tz text NOT NULL DEFAULT 'Asia/Kolkata',
    occurred_at timestamptz NOT NULL,
    corrected_at timestamptz,
    verify_mode text NOT NULL CHECK (verify_mode IN (
        'fingerprint', 'face', 'card', 'pin', 'palm', 'other'
    )),
    io_state text,
    work_code text,
    source text NOT NULL CHECK (source IN (
        'adms', 'zk_tcp', 'isapi', 'biotime', 'cosec', 'db_read', 'file'
    )),
    dedupe_key text NOT NULL,
    raw jsonb,
    received_at timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (occurred_at);

CREATE UNIQUE INDEX uq_punch_dedupe
    ON punch_events (device_id, dedupe_key, occurred_at);

CREATE INDEX idx_punch_org_seq ON punch_events (org_id, seq);

-- BRIN index on occurred_at for range scans
CREATE INDEX idx_punch_occurred_brin ON punch_events
    USING BRIN (occurred_at) WITH (pages_per_range = 32);

-- Default partition for out-of-range data
CREATE TABLE punch_events_default PARTITION OF punch_events DEFAULT;

-- Create partitions for current and next 3 months
DO $$
DECLARE
    m int;
    y int;
    start_date date;
    end_date date;
    part_name text;
BEGIN
    FOR i IN 0..3 LOOP
        start_date := date_trunc('month', CURRENT_DATE) + (i || ' months')::interval;
        end_date := start_date + '1 month'::interval;
        y := extract(year from start_date);
        m := extract(month from start_date);
        part_name := format('punch_events_%s_%s', y, lpad(m::text, 2, '0'));

        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF punch_events
             FOR VALUES FROM (%L) TO (%L)',
            part_name, start_date, end_date
        );
    END LOOP;
END
$$;

-- ===========================================================================
-- Sync checkpoints
-- ===========================================================================
CREATE TABLE sync_checkpoints (
    device_id uuid NOT NULL REFERENCES devices(id),
    kind text NOT NULL,
    cursor text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, kind)
);

-- ===========================================================================
-- Device commands
-- ===========================================================================
CREATE SEQUENCE device_command_seq;

CREATE TABLE device_commands (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    device_id uuid NOT NULL REFERENCES devices(id),
    cmd_no bigint NOT NULL UNIQUE DEFAULT nextval('device_command_seq'),
    type text NOT NULL,
    params jsonb,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN (
        'queued', 'sent', 'acknowledged', 'succeeded', 'failed', 'expired', 'blocked'
    )),
    attempts int NOT NULL DEFAULT 0,
    idempotency_key text NOT NULL,
    requested_by text,
    approved_by text,
    sent_at timestamptz,
    completed_at timestamptz,
    expires_at timestamptz,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, idempotency_key)
);

-- ===========================================================================
-- Outbox and webhooks
-- ===========================================================================
CREATE TABLE outbox (
    id bigserial PRIMARY KEY,
    org_id uuid NOT NULL,
    event_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz
);

CREATE TABLE webhook_subscriptions (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    url text NOT NULL,
    secret_ciphertext bytea NOT NULL,
    events text[] NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_deliveries (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id uuid NOT NULL REFERENCES webhook_subscriptions(id),
    outbox_id bigint NOT NULL REFERENCES outbox(id),
    attempt int NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'succeeded', 'failed')),
    response_code int,
    next_retry_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Jobs
-- ===========================================================================
CREATE TABLE jobs (
    id bigserial PRIMARY KEY,
    kind text NOT NULL,
    payload jsonb,
    run_at timestamptz NOT NULL DEFAULT now(),
    attempts int NOT NULL DEFAULT 0,
    locked_by text,
    locked_at timestamptz,
    last_error text,
    done_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Imports
-- ===========================================================================
CREATE TABLE imports (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    site_id uuid NOT NULL REFERENCES sites(id),
    device_id uuid,
    filename text NOT NULL,
    format text NOT NULL,
    mapping jsonb,
    status text NOT NULL DEFAULT 'pending',
    rows_total int NOT NULL DEFAULT 0,
    rows_ok int NOT NULL DEFAULT 0,
    rows_failed int NOT NULL DEFAULT 0,
    errors jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Reconciliation reports
-- ===========================================================================
CREATE TABLE reconciliation_reports (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id uuid NOT NULL REFERENCES organizations(id),
    device_id uuid NOT NULL REFERENCES devices(id),
    day date NOT NULL,
    stored_count int NOT NULL DEFAULT 0,
    replayed_new int NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pending',
    details jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ===========================================================================
-- Audit log (append-only, hash-chained)
-- ===========================================================================
CREATE TABLE audit_log (
    id bigserial PRIMARY KEY,
    org_id uuid,
    actor text NOT NULL,
    action text NOT NULL,
    target text,
    details jsonb,
    at timestamptz NOT NULL DEFAULT now(),
    prev_hash text,
    hash text NOT NULL
);

-- ===========================================================================
-- Row-Level Security policies
-- ===========================================================================

-- Grant table access to app and system roles
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO bip_app', tbl);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO bip_system', tbl);
    END LOOP;

    -- Grant sequence usage
    FOR tbl IN
        SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
    LOOP
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO bip_app', tbl);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO bip_system', tbl);
    END LOOP;
END
$$;

-- Enable RLS on org-scoped tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE sites FORCE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices FORCE ROW LEVEL SECURITY;
ALTER TABLE device_capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_capabilities FORCE ROW LEVEL SECURITY;
ALTER TABLE device_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_credentials FORCE ROW LEVEL SECURITY;
ALTER TABLE vendor_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE vendor_connections FORCE ROW LEVEL SECURITY;
ALTER TABLE gateways ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateways FORCE ROW LEVEL SECURITY;
ALTER TABLE gateway_pairing_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gateway_pairing_codes FORCE ROW LEVEL SECURITY;
ALTER TABLE people ENABLE ROW LEVEL SECURITY;
ALTER TABLE people FORCE ROW LEVEL SECURITY;
ALTER TABLE person_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE person_identities FORCE ROW LEVEL SECURITY;
ALTER TABLE punch_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE punch_events FORCE ROW LEVEL SECURITY;
ALTER TABLE device_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_commands FORCE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox FORCE ROW LEVEL SECURITY;
ALTER TABLE webhook_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_subscriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY;
ALTER TABLE imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE imports FORCE ROW LEVEL SECURITY;
ALTER TABLE reconciliation_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reconciliation_reports FORCE ROW LEVEL SECURITY;

-- RLS policies for bip_app: org_id = current_setting('app.org_id')
-- Organizations: policy on id (the org itself)
CREATE POLICY org_isolation ON organizations
    FOR ALL TO bip_app
    USING (id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (id = current_setting('app.org_id', true)::uuid);

-- All other org-scoped tables: policy on org_id column
CREATE POLICY site_isolation ON sites
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY device_isolation ON devices
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY device_cap_isolation ON device_capabilities
    FOR ALL TO bip_app
    USING (device_id IN (SELECT id FROM devices WHERE org_id = current_setting('app.org_id', true)::uuid))
    WITH CHECK (device_id IN (SELECT id FROM devices WHERE org_id = current_setting('app.org_id', true)::uuid));

CREATE POLICY device_cred_isolation ON device_credentials
    FOR ALL TO bip_app
    USING (device_id IN (SELECT id FROM devices WHERE org_id = current_setting('app.org_id', true)::uuid))
    WITH CHECK (device_id IN (SELECT id FROM devices WHERE org_id = current_setting('app.org_id', true)::uuid));

CREATE POLICY vc_isolation ON vendor_connections
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY gw_isolation ON gateways
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY gw_pair_isolation ON gateway_pairing_codes
    FOR ALL TO bip_app
    USING (gateway_id IN (SELECT id FROM gateways WHERE org_id = current_setting('app.org_id', true)::uuid))
    WITH CHECK (gateway_id IN (SELECT id FROM gateways WHERE org_id = current_setting('app.org_id', true)::uuid));

CREATE POLICY people_isolation ON people
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY pi_isolation ON person_identities
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY punch_isolation ON punch_events
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY cmd_isolation ON device_commands
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY outbox_isolation ON outbox
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY ws_isolation ON webhook_subscriptions
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

-- webhook_deliveries isolation via subscription
CREATE POLICY wd_isolation ON webhook_deliveries
    FOR ALL TO bip_app
    USING (subscription_id IN (
        SELECT id FROM webhook_subscriptions
        WHERE org_id = current_setting('app.org_id', true)::uuid
    ))
    WITH CHECK (subscription_id IN (
        SELECT id FROM webhook_subscriptions
        WHERE org_id = current_setting('app.org_id', true)::uuid
    ));

CREATE POLICY import_isolation ON imports
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

CREATE POLICY recon_isolation ON reconciliation_reports
    FOR ALL TO bip_app
    USING (org_id = current_setting('app.org_id', true)::uuid)
    WITH CHECK (org_id = current_setting('app.org_id', true)::uuid);

-- ===========================================================================
-- Partition maintenance function
-- ===========================================================================
CREATE OR REPLACE FUNCTION maintain_punch_partitions() RETURNS void AS $$
DECLARE
    i int;
    start_date date;
    end_date date;
    part_name text;
    y int;
    m int;
BEGIN
    FOR i IN 0..3 LOOP
        start_date := date_trunc('month', CURRENT_DATE) + (i || ' months')::interval;
        end_date := start_date + '1 month'::interval;
        y := extract(year from start_date);
        m := extract(month from start_date);
        part_name := format('punch_events_%s_%s', y, lpad(m::text, 2, '0'));

        IF NOT EXISTS (
            SELECT 1 FROM pg_class WHERE relname = part_name
        ) THEN
            EXECUTE format(
                'CREATE TABLE %I PARTITION OF punch_events
                 FOR VALUES FROM (%L) TO (%L)',
                part_name, start_date, end_date
            );
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE_SQL = """
DROP FUNCTION IF EXISTS maintain_punch_partitions();
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS reconciliation_reports CASCADE;
DROP TABLE IF EXISTS imports CASCADE;
DROP TABLE IF EXISTS jobs CASCADE;
DROP TABLE IF EXISTS webhook_deliveries CASCADE;
DROP TABLE IF EXISTS webhook_subscriptions CASCADE;
DROP TABLE IF EXISTS outbox CASCADE;
DROP TABLE IF EXISTS device_commands CASCADE;
DROP TABLE IF EXISTS sync_checkpoints CASCADE;
DROP TABLE IF EXISTS punch_events CASCADE;
DROP TABLE IF EXISTS raw_uploads CASCADE;
DROP TABLE IF EXISTS enrolments CASCADE;
DROP TABLE IF EXISTS person_identities CASCADE;
DROP TABLE IF EXISTS person_sites CASCADE;
DROP TABLE IF EXISTS people CASCADE;
DROP TABLE IF EXISTS gateway_pairing_codes CASCADE;
DROP TABLE IF EXISTS gateways CASCADE;
DROP TABLE IF EXISTS vendor_connections CASCADE;
DROP TABLE IF EXISTS device_credentials CASCADE;
DROP TABLE IF EXISTS device_capabilities CASCADE;
DROP TABLE IF EXISTS pending_devices CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS sites CASCADE;
DROP TABLE IF EXISTS organizations CASCADE;
DROP TABLE IF EXISTS staff_users CASCADE;
DROP TABLE IF EXISTS api_clients CASCADE;
DROP TABLE IF EXISTS partners CASCADE;
DROP SEQUENCE IF EXISTS punch_event_seq CASCADE;
DROP SEQUENCE IF EXISTS device_command_seq CASCADE;
DROP ROLE IF EXISTS bip_app;
DROP ROLE IF EXISTS bip_system;
"""


def upgrade() -> None:
    op.execute(UPGRADE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_SQL)
