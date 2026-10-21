# ADR-006: Tenancy hierarchy

## Status
Accepted

## Context
BIP serves multiple partners (LearnX, enterprise ERPs, and future apps), each managing multiple organizations (schools, companies), each with multiple sites and devices.

## Decision
Tenancy: partner -> organization (school, college, company) -> site -> device. People carry a `person_type` (student, staff, employee) and belong to sites.

## Consequences
- Partners are isolated: an API client can only access its partner's organizations.
- RLS enforces org-level isolation within a partner.
- Sites allow per-building or per-campus grouping of devices.
