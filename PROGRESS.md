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
**Status:** DONE
**Built:**
- **Rate Limiting (`src/bip/core/ratelimit.py`):** Thread-safe token bucket algorithm with per-key tracking (client token prefix or IP), burst controls (150 capacity, 120/min), and `RateLimitMiddleware` returning 429 Too Many Requests with `Retry-After` headers and exempt health check paths. Verified in `test_ratelimit.py`.
- **Secret Redaction (`src/bip/core/logging.py`):** Structlog redaction processor extended with recursive nested dict and list traversal. Automatically masks all sensitive keys (`password`, `secret`, `token`, `card_no`, `authorization`, `cookie`, `credential`, `api_key`, `access_token`, `refresh_token`, `biometric_data`, `fingerprint`, `face_template`), PIN masking (`10***`), and display name redaction. Verified in `test_redaction.py`.
- **Cryptographic Audit Chain (`src/bip/core/audit.py`):** SHA-256 hash chaining for all Ops Console audit log entries (`seq`, `prev_hash`, `entry_hash`, canonical JSON sorting). Chain verifier detects content tampering, link breaks, and deleted intermediate entries. Integrated into `bip.api.ops.store`. Verified in `test_audit_chain.py`.
- **Retention Purge Worker (`src/bip/workers/retention.py`):** Automated punch retention purge engine supporting both in-memory and PostgreSQL execution. Deletes records older than each tenant organization's configured `retention_days` (default 730d). Includes periodic worker loop with graceful shutdown. Verified in `test_retention.py`.
- **2,000-Device Load Test (`scripts/loadtest_2000_devices.py` & `docs/LOADTEST.md`):** Complete benchmark harness simulating 2,000 active biometric terminals sending 10,000 punches during morning peak hours over an async connection pool.
  - Latency p50: 1.71 ms
  - Latency p95: **3.05 ms** (SPEC: < 200 ms -> PASS)
  - Ingest lag p95: **0.003 s** (SPEC: < 60 s -> PASS)
  - Throughput: **500.8 req/s (2,504 punches/s)**
  - Error rate: **0.00%** (2,000 / 2,000 200 OK)
- **Terraform Skeleton (`deploy/terraform/`):** Production-ready infrastructure code (`main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`) for AWS deployment: VPC across 2 AZs, ALB with path routing (`/v1`, `/ops`, `/iclock`, `/gw`), Aurora PostgreSQL 16 cluster with automated snapshots, S3 Raw Inbox with 730-day lifecycle expiration, ECS Fargate cluster for API, Edge, and Worker services, Security Groups and IAM roles.
- **Agent Packaging Verification (`deploy/agent/`):** Complete packaging artifacts for edge gateway deployments (`bip-gateway.spec` PyInstaller spec, `winsw-service.xml` Windows service wrapper, `bip-gateway.service` systemd unit, `README_RPI.md` Raspberry Pi setup guide).
- **Compliance Documentation (`docs/compliance/`):**
  - `docs/compliance/DATA_MAP.md`: GDPR and DPDP Act 2023 data inventory, classification, legal grounds, and security safeguards.
  - `docs/compliance/BIOMETRIC_DATA_POLICY.md`: Enterprise policy draft detailing edge-only matching, template stripping guarantees, pseudonymization, and retention enforcement.
- **Operations Runbooks (`docs/runbooks/`):**
  - `docs/runbooks/disaster-recovery.md`: RPO < 15m, RTO < 60m, regional failover, raw inbox replay, deduplication idempotency.
  - `docs/runbooks/gateway-troubleshooting.md`: Outbox diagnostics, clock-skew triage, NTP synchronization, re-pairing workflows.
  - `docs/runbooks/database-maintenance.md`: Partition creation, partition detachment/dropping, RLS policy verification.
  - `docs/runbooks/certificate-rotation.md`: Gateway Ed25519 keypair rotation with dual-key grace periods, webhook HMAC secret rollover.
- **Developer Integration Guide (`docs/INTEGRATION.md`):** Comprehensive guide for LearnX and Saptta engineering teams (OAuth 2.0 auth, user provisioning, webhook HMAC verification in Python/Node.js, cursor polling, local feed API).
- **OpenAPI 3.1 Spec Export (`docs/openapi.json`):** Full 46-endpoint OpenAPI specification exported directly from FastAPI.
- **Root Documentation (`README.md`):** Complete architecture diagram (Mermaid), quickstart, test execution, Ops console guide, and documentation index.
**Evidence:** 204 unit tests pass across all suites; `ruff check` passes with 0 errors; `ruff format --check` passes with 105 files formatted; 2,000-device load test succeeds with p95 = 3.05ms (< 200ms) and ingest lag = 0.003s (< 60s); OpenAPI export generated with 46 routes.
**Next:** Production deployment and customer onboarding.

## Customer Self-Serve Web Console (Zero-Code Platform Administration)
**Status:** DONE
**Built:**
- **Biometric Machine Onboarding (`/ops/devices`):** Web form to register physical terminals (ZKTeco ADMS, Hikvision ISAPI, ZKBioTime, Matrix COSEC, TCP LAN standalone). Automatically whitelists device in `EdgeStore` and immediately displays hardware-specific setup instructions showing server address, port 8001, and step-by-step keypad/web instructions.
- **Organisation & School Management (`/ops/orgs`):** Web form to create institutions with Partner assignment, timezone selector, and retention days configuration.
- **Campus Gate / Site Management (`/ops/sites`):** Web form to create physical installation sites linked to organisations.
- **Software Integrations & Live Webhook Tester (`/ops/integrations`):** Connect consumer software (LearnX SIS, Saptta HRMS, Custom ERP). Generates HMAC-SHA256 signing secret. Includes live '⚡ Test' punch simulator that posts an authenticated punch payload and displays response status code and latency in milliseconds.
- **Attendance Spreadsheet Importer (`/ops/import`):** Upload CSV, Excel (.xlsx), or ZKTeco USB `attlog.dat` files with row-level validation, live punch ingestion into memory, and quarantine error breakdown.
- **1-Click Demo Login (`/ops/quick-login`):** Instant single-click authentication for non-technical customer evaluation.
**Evidence:** 209 unit tests pass (5 new for self-serve UI in `test_ops_console.py`); all routes smoke-tested and verified against live background server on port 8000; `ruff check` and `ruff format` 100% clean.

## People & Roster + Live Attendance Feed + Webhook Delivery Engine
**Status:** DONE
**Built:**
- **People & Roster (`/ops/people`):** Web form to create and manage students, employees, staff, visitors, and contractors. Auto-assigns sequential PINs from the org's `pin_range_start` (or accepts a manual override). Displays a full roster table with punch counts and a sidebar showing unmapped PINs seen from devices not yet linked to a person.
- **Live Attendance Feed (`/ops/attendance`):** Real-time punch viewer with stats panel (total punches, today's count, unique PINs seen, active devices, unmapped PINs). Filterable by organisation and verify mode (fingerprint / face / card / palm). Quick Simulate button fires a test punch directly from the page.
- **ADMS Live Ingest (`src/bip/edge/adms.py`):** ATTLOG uploads from ZKTeco push terminals now flow directly into the central punch pipeline via `add_test_punch`, making them immediately visible in the Attendance Feed and triggering webhook delivery.
- **Webhook Delivery Engine (`src/bip/api/delivery.py`):** Async, non-blocking webhook dispatch module. `dispatch_webhook` cryptographically signs each payload (HMAC-SHA256, `BIP-Signature` header), POSTs to consumer endpoints with 4 s timeout, and records every delivery (id, timestamp, status code, latency ms, error) in an in-memory log bounded at 100 entries. `trigger_punch_dispatch` fires background `asyncio.Task`s for all active webhooks matching the org on every new punch. Delivery logs are surfaced in the Integrations page.
- **Ops Console Sidebar updated** with People & Roster and Attendance Feed navigation links.
**Evidence:** 218 unit tests pass (9 new: 4 for People/Attendance pages in `test_ops_console.py`, 2 extra unauthenticated redirect cases for `/ops/people` and `/ops/attendance`, 2 for webhook delivery engine in `test_webhooks.py`, 1 for simulate-punch redirect check); `ruff check` and `ruff format` clean.


