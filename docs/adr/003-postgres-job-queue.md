# ADR-003: PostgreSQL as system of record and job queue

## Status
Accepted

## Context
The system needs a job queue for ingest, command fan-out, and webhook delivery. Adding Redis, Celery, or Kafka increases operational complexity for a service that starts small.

## Decision
PostgreSQL is both the system of record and the job queue. Use a transactional outbox pattern, `FOR UPDATE SKIP LOCKED` for worker claims, and `LISTEN/NOTIFY` for wake-ups. No Redis, Celery, or Kafka.

## Consequences
- Simpler ops: one database to back up, monitor, and scale.
- Job throughput is bounded by Postgres write capacity — acceptable for the initial scale.
- If throughput needs exceed Postgres, a dedicated queue can be introduced later.
