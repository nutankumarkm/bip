# ADR-002: One Python connector package for cloud and gateway

## Status
Accepted

## Context
Connectors need to run both in cloud workers (vendor pulls, file imports) and in the on-premise gateway agent.

## Decision
A single package `bip.connectors` contains all connector implementations. It runs in cloud workers and is also bundled into the gateway agent.

## Consequences
- Shared code, shared tests, one conformance suite.
- Gateway-only dependencies (pyzk, pyodbc) are optional extras.
- The connector interface must work in both async cloud and sync gateway contexts.
