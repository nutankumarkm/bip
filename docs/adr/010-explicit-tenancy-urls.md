# ADR-010: Tenancy is explicit in URLs

## Status
Accepted

## Context
Multi-tenant APIs can encode tenancy in headers, subdomains, or URL paths. Explicit URL paths are easiest to audit, log, and test.

## Decision
Tenancy is explicit in URLs: `/v1/orgs/{org_id}/...`. An API client belongs to a partner and can only access that partner's organizations.

## Consequences
- Clear, auditable access patterns in logs and monitoring.
- Every org-scoped request validates partner ownership before setting `app.org_id`.
- No ambient tenant context that could leak across requests.
