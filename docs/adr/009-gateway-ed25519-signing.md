# ADR-009: Gateway authenticates by Ed25519 request signing

## Status
Accepted

## Context
Gateways sit behind school networks that often have TLS-intercepting proxies (for content filtering), which break mTLS client certificates. The gateway needs a robust authentication mechanism.

## Decision
Gateways authenticate by Ed25519 request signing with a key pair created at pairing. The signature covers method, path, timestamp, and body hash, preventing replay and tampering.

## Consequences
- Survives TLS-intercepting proxies that break mTLS.
- Clock skew tolerance of 300 seconds.
- Private key stored with OS-level protection (DPAPI on Windows, file permissions on Linux).
- No dependency on certificate infrastructure.
