# ADR-008: FastAPI + Jinja2/HTMX ops console

## Status
Accepted

## Context
BIP needs an internal operations console for platform admins. The team's strength is Python; a separate SPA (React, Next.js) adds build complexity and a second deployment.

## Decision
FastAPI serves the consumer API, gateway API, and a server-rendered Jinja2 + HTMX ops console. No SPA, no Next.js.

## Consequences
- One Python process serves everything.
- HTMX provides dynamic interactions without client-side JavaScript frameworks.
- The console is internal-only, behind email + password + TOTP authentication.
