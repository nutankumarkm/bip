# Biometric Integration Platform (BIP)

A multi-tenant service connecting biometric attendance terminals (fingerprint, face, card) at Indian schools, colleges, and SMB employers to consumer applications.

## Quick Start

```bash
# Create virtual environment and install
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -e ".[dev]"

# Run tests
make test

# Lint
make lint

# Start services (requires Docker)
make up

# Run demo with emulated devices
make demo
```

## Architecture

BIP connects biometric devices through four modes:
1. **Device Push (default)** — terminals speak ADMS/iClock protocol directly to BIP's Device Edge
2. **Vendor Platform** — BIP pulls from vendor servers (ZKBioTime, Matrix COSEC)
3. **Local Gateway** — Python agent on a school PC reaches LAN-only devices
4. **File Import** — CSV, XLSX, or USB exports as last resort

## Consumers

- **LearnX** — Python desktop school-management app (first consumer)
- **Saptta HR** — Django HRMS for SMBs (second consumer)
- **Partner apps** — third-party integrations via the public API

## Documentation

- `BUILD_PROMPT.md` — Full specification
- `PROGRESS.md` — Build progress and status
- `CLAUDE.md` — Session conventions and make targets
- `docs/adr/` — Architecture Decision Records
- `docs/CAPABILITIES.md` — Device capability matrix (generated)
- `docs/LAB_VERIFICATION.md` — Lab verification status
