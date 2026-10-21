# BIP Connector Capability Matrix

> Generated automatically from `src/bip/connectors/registry.yaml`.

## Status Definitions

- **declared**: Claimed by vendor or open-source protocol documentation.
- **probed**: Device successfully answered probe query at runtime.
- **verified**: Certified in hardware device lab against real physical hardware.
- **unsupported**: Known to be unsupported on this model family.

### `zk_adms` (PUSH)

**Description:** ZKTeco ADMS / iClock HTTP push protocol

#### Model Pattern: `ZK-ADMS-*`
*ZKTeco and eSSL ADMS firmware terminals*

| Capability | Status |
|---|---|
| `punches.stream` | 🔵 **declared** |
| `punches.replay` | 🔵 **declared** |
| `people.read` | 🔵 **declared** |
| `people.write` | 🔵 **declared** |
| `people.delete` | 🔵 **declared** |
| `enrol.remote` | 🔵 **declared** |
| `device.time.set` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `templates.relay` | ❌ **unsupported** |
| `logs.clear` | 🔵 **declared** |

### `zk_tcp` (PULL)

**Description:** ZKTeco standalone binary protocol over TCP 4370

#### Model Pattern: `ZK-TCP-*`
*Standalone terminals via pyzk adapter*

| Capability | Status |
|---|---|
| `punches.pull` | 🔵 **declared** |
| `people.read` | 🔵 **declared** |
| `people.write` | 🔵 **declared** |
| `people.delete` | 🔵 **declared** |
| `device.time.set` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `templates.relay` | ❌ **unsupported** |

### `hik_isapi` (PULL)

**Description:** Hikvision Access Control ISAPI HTTP/HTTPS

#### Model Pattern: `DS-K1T*`
*Hikvision MinMoe face & card terminals (DS-K1T671, DS-K1T341, etc.)*

| Capability | Status |
|---|---|
| `punches.pull` | 🔵 **declared** |
| `people.read` | 🔵 **declared** |
| `people.write` | 🔵 **declared** |
| `people.delete` | 🔵 **declared** |
| `device.time.set` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `templates.relay` | ❌ **unsupported** |

### `biotime` (VENDOR)

**Description:** ZKBioTime server REST API pull

#### Model Pattern: `ZKBioTime-8.5+`
*ZKBioTime 8.5/9.0 central attendance server*

| Capability | Status |
|---|---|
| `punches.pull` | 🔵 **declared** |
| `people.read` | 🔵 **declared** |
| `people.write` | 🔵 **declared** |
| `people.delete` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `device.time.set` | ❌ **unsupported** |

### `cosec` (VENDOR)

**Description:** Matrix COSEC enterprise integration (stub)

#### Model Pattern: `Matrix-COSEC-*`
*Matrix COSEC server (requires site license and Matrix API manual)*

| Capability | Status |
|---|---|
| `punches.pull` | ❌ **unsupported** |
| `people.read` | ❌ **unsupported** |
| `people.write` | ❌ **unsupported** |
| `people.delete` | ❌ **unsupported** |
| `device.info` | ❌ **unsupported** |

### `db_read` (PULL)

**Description:** eTimeTrackLite SQL Server / Access read-only integration

#### Model Pattern: `eTimeTrackLite-*`
*Direct ODBC database query (DeviceLogs monthly tables)*

| Capability | Status |
|---|---|
| `punches.pull` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `people.read` | ❌ **unsupported** |
| `people.write` | ❌ **unsupported** |
| `people.delete` | ❌ **unsupported** |
| `device.time.set` | ❌ **unsupported** |

### `file_import` (FILE)

**Description:** Manual export file import (CSV, XLSX, ZK USB attlog.dat)

#### Model Pattern: `File-Import-*`
*Row-validated file imports with automatic deduplication*

| Capability | Status |
|---|---|
| `punches.pull` | 🔵 **declared** |
| `device.info` | 🔵 **declared** |
| `people.read` | ❌ **unsupported** |
| `people.write` | ❌ **unsupported** |
| `people.delete` | ❌ **unsupported** |
| `device.time.set` | ❌ **unsupported** |
