# BIP — Biometric Integration Platform

## First steps for any session

1. Read `BUILD_PROMPT.md` for the full specification.
2. Read `PROGRESS.md` to find the first unfinished milestone.
3. Resume from that milestone.

## Stack

- Python 3.12, pip + venv (uv unavailable in this environment)
- FastAPI, uvicorn, pydantic v2, pydantic-settings
- SQLAlchemy 2 (async) + asyncpg; Alembic
- PostgreSQL 16
- httpx, structlog (JSON logs with redaction)
- Jinja2 + HTMX (ops console)
- cryptography (Ed25519, AES-256-GCM), argon2-cffi, pyotp
- pytest, pytest-asyncio, respx
- ruff (lint + format); mypy strict on `bip.sdk` and `bip.core`
- Docker + docker compose

## Conventions

- Source in `src/bip/`, tests in `tests/`
- RLS on every org-scoped table; `bip_app` role with FORCE ROW LEVEL SECURITY
- No secrets in logs; structlog redaction processor active
- ADRs in `docs/adr/NNN-title.md`
- Commits prefixed with milestone: `M3: ADMS edge, ingest, emulator`

## Make targets

```
make up        # docker compose up
make down      # docker compose down
make test      # pytest (no e2e)
make test-all  # pytest (all)
make lint      # ruff check + format check
make fmt       # ruff fix + format
make typecheck # mypy strict on sdk and core
make migrate   # alembic upgrade head
make seed      # seed dev data
make demo      # full demo with emulators
make loadtest  # 2000-device load test
```

## Key directories

- `src/bip/core/` — settings, db, tenancy, crypto, audit, logging
- `src/bip/sdk/` — connector protocols, PunchEvent, capabilities, errors
- `src/bip/connectors/` — device protocol adapters
- `src/bip/edge/` — ADMS/iClock push endpoints (port 8081)
- `src/bip/api/` — consumer API, gateway API, ops console (port 8080)
- `src/bip/workers/` — ingest, commands, delivery, scheduler
- `src/bip/gateway/` — gateway agent
- `src/bip/emulators/` — device emulators and mock servers
- `clients/python/bip_client/` — Python client library
