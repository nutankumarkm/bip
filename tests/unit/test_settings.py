"""Tests for BIP settings module."""

import base64

import pytest

from bip.core.settings import Settings


@pytest.mark.unit
def test_settings_defaults():
    s = Settings()
    assert s.edge_port == 8081
    assert s.api_port == 8080
    assert s.jwt_expiry_minutes == 15
    assert s.gateway_clock_skew_max_seconds == 300


@pytest.mark.unit
def test_master_key_bytes():
    raw = b"test-key-32-bytes-for-dev"
    encoded = base64.b64encode(raw).decode()
    s = Settings(master_key=encoded)
    assert s.master_key_bytes == raw


@pytest.mark.unit
def test_settings_log_format_validation():
    s = Settings(log_format="console")
    assert s.log_format == "console"
    s = Settings(log_format="json")
    assert s.log_format == "json"
