# ADR-001: Device push is the default mode

## Status
Accepted

## Context
Biometric terminals can connect via push (ADMS/iClock), vendor platform, local gateway, or file import. Schools often lack static IPs and IT staff to maintain local software.

## Decision
Device push via ADMS/iClock is the default and recommended connection mode. The gateway is the second option for LAN-only devices.

## Consequences
- The Device Edge must handle direct connections from terminals on diverse networks.
- No dependency on a local PC or vendor cloud for the default path.
- Devices that cannot speak ADMS require the gateway or vendor platform path.
