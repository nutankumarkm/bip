# ADR-012: Punch feed ordered by ingest sequence, not punch time

## Status
Accepted

## Context
Punches can arrive late — a gateway reconnecting after hours offline, a file import of last week's data, or a replay reconciliation. Ordering by punch time would miss late arrivals that fall before a consumer's cursor.

## Decision
The punch feed is ordered by ingest sequence (`seq`), a monotonically increasing bigint assigned at insert time. Consumers cursor by `seq`, not by `occurred_at`.

## Consequences
- Late-arriving punches are never missed by consumers who poll forward.
- Consumers see punches in arrival order, not chronological order.
- The consumer is responsible for sorting by `occurred_at` if needed.
