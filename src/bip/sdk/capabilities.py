"""Connector capabilities enumeration."""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    PUNCHES_STREAM = "punches.stream"
    PUNCHES_PULL = "punches.pull"
    PUNCHES_REPLAY = "punches.replay"
    PEOPLE_READ = "people.read"
    PEOPLE_WRITE = "people.write"
    PEOPLE_DELETE = "people.delete"
    ENROL_REMOTE = "enrol.remote"
    TIME_SET = "device.time.set"
    DEVICE_INFO = "device.info"
    TEMPLATES_RELAY = "templates.relay"
    LOGS_CLEAR = "logs.clear"
