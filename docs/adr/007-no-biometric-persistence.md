# ADR-007: Biometric templates and punch photos never persist in BIP

## Status
Accepted

## Context
Biometric templates (fingerprints, face data) and punch photos are highly sensitive personal data under India's DPDP Act. Storing them increases compliance burden and breach risk.

## Decision
The Edge strips template fields from all uploads and never requests photos. BIP stores only enrolment counts and flags (number of fingerprints, face enrolled yes/no), never the biometric data itself.

## Consequences
- Reduced data protection liability.
- Templates stay on devices where they are used for matching.
- `TEMPLATES_RELAY` capability exists in the enum but is never enabled in this build.
- `TransFlag` in ADMS handshake omits photo and template transfer.
