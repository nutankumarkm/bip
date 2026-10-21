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
**Status:** NOT STARTED

## M3 — Push ingestion
**Status:** NOT STARTED

## M4 — Consumer API and delivery
**Status:** NOT STARTED

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
