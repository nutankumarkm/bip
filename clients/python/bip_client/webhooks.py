"""Webhook signature verification for BIP consumers."""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_webhook(header: str, body: str, secret: str, tolerance_seconds: int = 300) -> bool:
    parts = {}
    for segment in header.split(","):
        key, _, value = segment.partition("=")
        parts[key.strip()] = value.strip()

    ts_str = parts.get("t", "")
    provided_sig = parts.get("v1", "")
    if not ts_str or not provided_sig:
        return False

    try:
        ts = int(ts_str)
    except ValueError:
        return False

    if abs(time.time() - ts) > tolerance_seconds:
        return False

    expected_message = f"{ts}.{body}"
    expected_sig = hmac.new(secret.encode(), expected_message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)
