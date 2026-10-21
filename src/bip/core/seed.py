"""Seed dev data: one partner, one API client, one org, one site, one staff admin."""

from __future__ import annotations

import hashlib
import secrets

import pyotp
from argon2 import PasswordHasher

ph = PasswordHasher()

SEED_SQL = """
-- Seed: LearnX partner
INSERT INTO partners (id, name)
VALUES ('a0000000-0000-0000-0000-000000000001', 'LearnX')
ON CONFLICT DO NOTHING;

-- Seed: API client with all scopes
INSERT INTO api_clients (id, partner_id, name, client_id, secret_hash, scopes, active)
VALUES (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'LearnX Dev Client',
    'learnx-dev',
    '{secret_hash}',
    ARRAY['orgs:write','devices:read','devices:write','people:write','punches:read',
          'commands:write','webhooks:write','imports:write','gateways:write'],
    true
)
ON CONFLICT DO NOTHING;

-- Seed: organization
INSERT INTO organizations (id, partner_id, type, name, timezone, retention_days, pin_range_start)
VALUES (
    'c0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    'school',
    'Demo School',
    'Asia/Kolkata',
    730,
    10001
)
ON CONFLICT DO NOTHING;

-- Seed: site
INSERT INTO sites (id, org_id, name, timezone, active_hours, active)
VALUES (
    'd0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'Main Campus',
    'Asia/Kolkata',
    '{{"Mon": ["07:00", "18:00"], "Tue": ["07:00", "18:00"], "Wed": ["07:00", "18:00"],
      "Thu": ["07:00", "18:00"], "Fri": ["07:00", "18:00"], "Sat": ["07:00", "14:00"]}}'::jsonb,
    true
)
ON CONFLICT DO NOTHING;

-- Seed: staff admin
INSERT INTO staff_users (id, email, password_hash, totp_secret_enc, role, active)
VALUES (
    'e0000000-0000-0000-0000-000000000001',
    'admin@bip.local',
    '{admin_password_hash}',
    NULL,
    'platform_admin',
    true
)
ON CONFLICT DO NOTHING;
"""


def main() -> None:
    from sqlalchemy import create_engine, text

    from bip.core.settings import settings

    client_secret = secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
    admin_password = "admin-dev-password"
    admin_hash = ph.hash(admin_password)
    totp_secret = pyotp.random_base32()

    sql = SEED_SQL.format(
        secret_hash=secret_hash,
        admin_password_hash=admin_hash.replace("'", "''"),
    )

    engine = create_engine(settings.database_url_sync)
    with engine.begin() as conn:
        conn.execute(text(sql))

    print("=== Seed complete ===")
    print("API client_id: learnx-dev")
    print(f"API client_secret: {client_secret}")
    print("Admin email: admin@bip.local")
    print(f"Admin password: {admin_password}")
    print(f"TOTP secret (set up in authenticator): {totp_secret}")
    print("Org ID: c0000000-0000-0000-0000-000000000001")
    print("Site ID: d0000000-0000-0000-0000-000000000001")


if __name__ == "__main__":
    main()
