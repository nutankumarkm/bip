"""Deduplication utilities for punch events."""

from __future__ import annotations

import hashlib


def compute_dedupe_key(device_identity: str, device_pin: str, device_local_time_str: str, verify_mode: str) -> str:
    payload = f"{device_identity}|{device_pin}|{device_local_time_str}|{verify_mode}"
    return hashlib.sha256(payload.encode()).hexdigest()
