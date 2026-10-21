# Lab Verification Status

Items marked `TODO(lab)` in the codebase require physical device testing. This document tracks their verification status.

## ADMS/iClock Protocol
| Item | Status | Notes |
|---|---|---|
| TimeZone handshake field format (hours vs minutes) | TODO(lab) | Need to test with actual eSSL/ZKTeco device |
| ATTLOGStamp reset for backfill | TODO(lab) | |
| Per-device secret support | TODO(lab) | Firmware-dependent |
| Face enrolment command format | TODO(lab) | |
| DATA QUERY ATTLOG replay | TODO(lab) | |
| DATA QUERY USERINFO for full user list | TODO(lab) | |
| Push 2.x firmware endpoints | TODO(lab) | /iclock/push, /iclock/registry |
| OPERLOGStamp reset | TODO(lab) | |

## ZK TCP (pyzk)
| Item | Status | Notes |
|---|---|---|
| pyzk API stability | TODO(lab) | Unofficial library, pinned version |

## Hikvision ISAPI
| Item | Status | Notes |
|---|---|---|
| Event minor codes for verification-passed | TODO(lab) | Per-model config table needed |
| HTTP event notification support | TODO(lab) | |

## BioTime
| Item | Status | Notes |
|---|---|---|
| JWT vs Token auth variants | TODO(lab) | Version-dependent |

## eTimeTrackLite
| Item | Status | Notes |
|---|---|---|
| Table/column naming (DeviceLogs_M_YYYY) | TODO(lab) | |

## Clock Drift
| Item | Status | Notes |
|---|---|---|
| ADMS drift estimation accuracy | TODO(lab) | Median of recent real-time samples |
