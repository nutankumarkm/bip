# BIP Build Progress

## M0 — Scaffold
**Status:** DONE
**Built:** git repo, directory structure, pyproject.toml, Makefile, docker-compose.yml, Dockerfile, settings, logging, db module, API and Edge app stubs, worker main, CLAUDE.md, .gitignore, .env.example, ADRs 001-013, CI workflow, alembic config, README, LAB_VERIFICATION.md
**Evidence:** `ruff check` and `ruff format --check` pass; 11 pytest tests pass (settings, logging redaction, API/Edge health)
**Open issues:** uv unavailable — using pip + venv as fallback; Docker compose health not tested yet (no DB migration)
**Next:** M1 — Data model and tenancy migrations

## M1 — Data and tenancy
**Status:** DONE
**Built:** Initial migration with all 27 tables, punch_events partitioned by month (current + 3 ahead + default), bip_app and bip_system roles, RLS policies on all org-scoped tables with FORCE ROW LEVEL SECURITY, partition maintenance function, seed script (partner, API client, org, site, staff admin)
**Evidence:** 16 unit tests pass (including 5 schema validation tests); lint clean; integration tests written for RLS isolation and partition maintenance (require Postgres)
**Open issues:** Integration tests not run yet (need Docker compose up + migrate); person_sites table has no org_id (RLS via join to people)
**Next:** M2 — SDK

## M2 — SDK
**Status:** DONE
**Built:** Capability enum (11 capabilities), Connector and PushConnector protocols, PunchEvent/RawPunch/DevicePerson/CommandResult/ProbeResult/HealthReport models, dedupe_key computation (SHA-256), error taxonomy (6 error types with problem_type mapping), DeviceCommand/ParsedUpload, conformance harness
**Evidence:** 36 unit tests pass (20 new SDK tests); lint and format clean
**Open issues:** None
**Next:** M3 — Push ingestion (Edge, raw inbox, ingest worker, ADMS emulator)

## M3 — Push ingestion
**Status:** DONE
**Built:** ADMS/iClock parser (ATTLOG, OPERLOG, command results, template stripping, handshake/command rendering), Edge FastAPI app with full ADMS endpoint set (handshake, upload, getrequest, devicecmd, ping, registry, push), EdgeStore abstraction (in-memory for tests, Postgres-ready), pending device tracking, unknown serial rejection (ADR-011), ADMS device emulator with N virtual devices
**Evidence:** 66 unit tests pass (30 new for M3); lint clean; parser handles 1000 punches, templates stripped, unknown serials refused with 403, pending devices tracked
**Open issues:** Ingest worker processes raw_uploads in-memory only (Postgres-backed processing deferred to integration with Docker Compose); emulator→Edge e2e test needs running services
**Next:** M4 — Consumer API and delivery

## M4 — Consumer API and delivery
**Status:** DONE
**Built:** OAuth2 client credentials with JWT (15-min tokens, SHA-256 hashed secrets), scope-based authorization, partner→org access control, Consumer API v1 (orgs, sites, devices, cursor-based punch feed ordered by seq, unmapped-pins, webhooks CRUD), webhook signing/verification (HMAC-SHA256 with `t=<unix>,v1=<hex>`), Python client library (BIPClient with token caching + iter_punches + upsert/delete person, LocalFeedClient for gateway), consumer-side webhook verification helper
**Evidence:** 83 unit tests pass (17 new for M4 — OAuth, orgs, sites, devices, cursor feed, unmapped PINs, webhooks, cross-partner denial, webhook signatures); lint and format clean
**Open issues:** In-memory stores for API testing (Postgres-backed in Docker Compose); JWT InsecureKeyLength warning in tests (default test secret < 32 bytes — prod uses longer key)
**Next:** M5 — People and commands

## M5 — People and commands
**Status:** DONE
**Built:** People CRUD (PUT upsert by external_ref with auto PIN allocation, GET, list with active/site filters, DELETE), person identity management (sequential PINs from org's pin_range_start), enrolment tracking endpoints (per-person, per-device), command queue (create with idempotency, list with device/state filters, get), command fan-out (set_user/delete_user commands auto-created when people are upserted/deleted to all site devices), match suggestions (rapidfuzz-based name similarity + PIN matching), reconciliation (expected vs enrolled comparison), extended Python client library
**Evidence:** 114 unit tests pass (31 new for M5); lint and format clean
**Open issues:** In-memory stores (Postgres-backed in Docker Compose); match suggestions use simple name-PIN similarity (ADR-013 says matching is consumer's job, BIP just provides suggestions)
**Next:** M6 — Gateway

## M6 — Gateway
**Status:** DONE
**Built:** Ed25519 request signing/verification (ADR-009, canonical message `<METHOD>\n<path with query>\n<timestamp>\n<sha256 hex>` with base64 signatures, clock skew checks <300s); signed Gateway API under `/gw/v1` (pairing, config, long-poll commands, idempotent batch punch upload, command execution result, heartbeat, LAN discovery reporting, signed release manifest); consumer gateway endpoints under `/v1/orgs/{org_id}/gateways` (8-digit pairing code valid 15m, list, get, revoke, device assignment); Gateway agent (`bip.gateway` CLI with pair and run, SQLite outbox in WAL mode, `DevicePoller`, `OutboxUploader` with exponential backoff, `CommandRunner`, `HeartbeatSender`, `local_feed` API server on localhost:47800 with token auth for LearnX, `NetworkDiscovery` subnet scanner, `AgentUpdater` with signature verification, staging, swap and rollback); `zk_tcp` connector adapter isolating pyzk and implementing BIP SDK `Connector` protocol; `FakeZKClient` emulator; packaging in `deploy/agent/` (PyInstaller spec, WinSW service XML, systemd unit, Raspberry Pi deployment guide).
**Evidence:** 137 unit tests pass (23 new for M6); ruff check and format clean; simulated 72h offline period (1,200 punches across multiple devices) syncs with zero loss; batch upload idempotency verified; tampered signatures, tampered payloads, and clock skew >300s rejected.
**Open issues:** In-memory stores for API testing (Postgres-backed in Docker Compose); DPAPI fallback to file when pywin32 is not installed.
**Next:** M7 — More connectors (hik_isapi, biotime, db_read, file_import, cosec stub, capability registry, docs/CAPABILITIES.md)

## M7 — More connectors
**Status:** DONE
**Built:** 
- `hik_isapi`: Hikvision ISAPI pull adapter (multipart MIME response parsing, XML/JSON event parsing, offset-aware datetime normalization, cursor-based poll, user/card provision, reboot command, real-time alert event stream). Emulated with `HikISAPIMock`.
- `biotime`: ZKTeco BioTime 8.5/Cloud REST API adapter (token auth with auto-refresh, `/personnel/api/iclock/`, transaction querying with cursor, user/card push). Emulated with `BioTimeMock`.
- `db_read`: Read-only SQL database poller (Postgres, MySQL, SQL Server, SQLite via SQLAlchemy) with cursor tracking on incremental column (`punch_time` or `id`), column mapping, schema isolation.
- `file_import`: CSV and XLSX punch parser (`FileImporter` with smart column detection for PIN, timestamp, device_id, in_out; validation, invalid row quarantine, import report summary) + `FileImportAdapter` + Consumer API endpoint `POST /v1/orgs/{org_id}/imports/punches`.
- `cosec`: Matrix COSEC stub adapter raising `NotSupportedError(Capability.LIVE_EVENTS)` with clear unsupported reason.
- `registry.yaml`: Declarative connector capability registry for all 6 connectors (`zk_tcp`, `hik_isapi`, `biotime`, `db_read`, `file_import`, `cosec`) specifying pull/push capabilities, wire protocols, auth mechanisms, and sample configs.
- `docs/CAPABILITIES.md`: Generated capability matrix document with comparison table, detail cards, and config examples.
**Evidence:** 157 unit tests pass (20 new for M7); conformance test passes for all connectors; malformed rows rejected with structured import report; offset/naive timezone bugs fixed; lint clean.
**Open issues:** Database connector tests use SQLite in-memory engine.
**Next:** M8 — Ops console

## M8 — Ops console
**Status:** DONE
**Built:**
- Ops console web application (`bip.api.ops`) using server-rendered Jinja2 templates + HTMX (ADR-008) with dark theme UI.
- Authentication & Security (`auth.py`): console admin credentials (PBKDF2-HMAC-SHA256 password hashing), TOTP second factor (pyotp, 30s window), cryptographically random session tokens (32 bytes urlsafe), CSRF token generation and validation on state-modifying actions.
- Ops In-Memory Stores (`store.py`): `AuditEntry` logging all administrative actions (actor, action, resource_type, resource_id, timestamp, detail), `ApprovalRequest` two-person rule approval queue, `_PARTNERS` registry.
- Ops Router (`router.py`) & Pages (`templates/ops_*.html`):
  - `/ops/login`: Email + password authentication with error handling.
  - `/ops/totp`: 6-digit TOTP verification step before session activation.
  - `/ops/`: Operational dashboard with live metrics (partners, orgs, sites, devices, gateways, pending approvals) and recent audit logs.
  - `/ops/partners`: Partner management with create partner form.
  - `/ops/orgs`: Multi-tenant organization list with partner filtering.
  - `/ops/sites`: Physical site listing with device counts.
  - `/ops/devices`: Device fleet overview with vendor, model, and status.
  - `/ops/gateways`: Edge gateway pairing management with approval-gated revocation requests.
  - `/ops/approvals`: Two-person rule approval queue (requestor cannot self-approve, status tracking).
  - `/ops/audit`: Searchable and filterable audit trail by resource type and actor with pagination.
**Evidence:** 184 unit tests pass (27 new for M8 in `test_ops_console.py`); all pages smoke tested; unauthenticated redirects verified; wrong password & wrong TOTP rejected; CSRF enforcement verified; two-person approval enforced (self-approval strictly prohibited); Starlette keyword-arg TemplateResponse fix verified.
**Open issues:** In-memory session and audit storage (Postgres-backed in Docker Compose).
**Next:** M9 — Hardening and handover

## M9 — Hardening and handover
**Status:** NOT STARTED

