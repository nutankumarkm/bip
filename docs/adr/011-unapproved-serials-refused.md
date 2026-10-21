# ADR-011: Unapproved serials get handshake replies but uploads are refused

## Status
Accepted

## Context
Devices with unknown serial numbers will dial in to the Edge. We need to discover them without ingesting unverified data.

## Decision
Unapproved (unknown) serials receive handshake and heartbeat replies so they appear as pending in the ops console. Their data uploads are refused with HTTP 403. Records stay on the device until the serial is claimed to an org.

## Consequences
- Devices are discoverable without risk of ingesting rogue data.
- No data loss: records stay on-device until approved.
- The `pending_devices` table tracks unknown serials with first/last seen timestamps.
