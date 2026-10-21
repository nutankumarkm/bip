# ADR-013: Device-user to student matching happens in the consumer

## Status
Accepted

## Context
Matching device users (identified by PIN and name) to students or employees requires the roster, which only the consumer app holds. BIP does not have admission lists, roll numbers, or HR records.

## Decision
Matching is the consumer's responsibility. BIP offers a stateless suggestion endpoint (`match-suggestions`) that takes a candidate roster and returns matches by exact PIN, fuzzy name, and card number. BIP stores only display name, person type, PIN, and card number — not the full identity.

## Consequences
- BIP stays decoupled from roster formats and matching rules.
- The consumer has full control over match acceptance.
- BIP's `people` table is minimal: external_ref, display_name, person_type, device_pin, card_no.
