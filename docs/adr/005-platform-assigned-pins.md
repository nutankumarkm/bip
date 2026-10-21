# ADR-005: Platform-assigned numeric PINs with adoption

## Status
Accepted

## Context
Biometric devices identify users by numeric PINs. Schools may already have PINs (admission numbers) assigned on devices. New users need unique PINs.

## Decision
New people get platform-assigned numeric PINs, unique per org, starting from `pin_range_start`. Existing device PINs are adopted at onboarding via the `device_pin` field on person creation.

## Consequences
- No PIN collisions within an org.
- Existing device setups are preserved during onboarding.
- PIN reuse within the retention period is prevented.
