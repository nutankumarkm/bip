"""BIP Connector SDK — capabilities, protocols, events, errors."""

from bip.sdk.capabilities import Capability
from bip.sdk.dedupe import compute_dedupe_key
from bip.sdk.errors import (
    AuthFailed,
    CapacityFull,
    ConnectorError,
    DeviceBusy,
    ProtocolError,
    Unreachable,
    Unsupported,
)
from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    PunchEvent,
    RawPunch,
)
from bip.sdk.protocols import Connector, DeviceCommand, ParsedUpload, PushConnector

__all__ = [
    "AuthFailed",
    "Capability",
    "CapacityFull",
    "Checkpoint",
    "CommandResult",
    "Connector",
    "ConnectorError",
    "DeviceBusy",
    "DeviceCommand",
    "DevicePerson",
    "DeviceTarget",
    "HealthReport",
    "ParsedUpload",
    "ProbeResult",
    "ProtocolError",
    "PunchEvent",
    "PushConnector",
    "RawPunch",
    "Unreachable",
    "Unsupported",
    "compute_dedupe_key",
]
