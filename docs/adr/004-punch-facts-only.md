# ADR-004: BIP stores punch facts, never attendance policy

## Status
Accepted

## Context
Attendance policy (present, late, half-day, leave) varies by school, college, and employer. Building policy into BIP would couple it to every consumer's rules.

## Decision
BIP stores raw punch events — who punched where, when, and how. Attendance policy, notifications, and payroll belong to consumer applications (LearnX and enterprise ERPs).

## Consequences
- BIP's scope is well-bounded: ingest, store, deliver, manage devices.
- Consumers own the interpretation of punches.
- No parent notifications, payroll calculations, or school-facing attendance screens in BIP.
