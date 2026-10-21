"""Connector error taxonomy."""

from __future__ import annotations


class ConnectorError(Exception):
    problem_type: str = "connector_error"

    def __init__(self, message: str, *, device_id: str | None = None) -> None:
        super().__init__(message)
        self.device_id = device_id


class Unreachable(ConnectorError):
    problem_type = "device_unreachable"


class AuthFailed(ConnectorError):
    problem_type = "auth_failed"


class Unsupported(ConnectorError):
    problem_type = "capability_unsupported"


class ProtocolError(ConnectorError):
    problem_type = "protocol_error"


class DeviceBusy(ConnectorError):
    problem_type = "device_busy"


class CapacityFull(ConnectorError):
    problem_type = "capacity_full"


ERROR_MAP: dict[str, type[ConnectorError]] = {
    "device_unreachable": Unreachable,
    "auth_failed": AuthFailed,
    "capability_unsupported": Unsupported,
    "protocol_error": ProtocolError,
    "device_busy": DeviceBusy,
    "capacity_full": CapacityFull,
}
