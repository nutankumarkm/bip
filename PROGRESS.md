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
**Status:** NOT STARTED

## M6 — Gateway
**Status:** NOT STARTED

## M7 — More connectors
**Status:** NOT STARTED

## M8 — Ops console
**Status:** NOT STARTED

## M9 — Hardening and handover
**Status:** NOT STARTED
