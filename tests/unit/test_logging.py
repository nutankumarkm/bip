"""Tests for BIP logging module."""

import pytest

from bip.core.logging import REDACTED, _redact_processor


@pytest.mark.unit
def test_redact_password():
    event = {"event": "login", "password": "secret123"}
    result = _redact_processor(None, "info", event)
    assert result["password"] == REDACTED


@pytest.mark.unit
def test_redact_token():
    event = {"event": "auth", "token": "eyJ..."}
    result = _redact_processor(None, "info", event)
    assert result["token"] == REDACTED


@pytest.mark.unit
def test_redact_card_no():
    event = {"event": "sync", "card_no": "1234567890"}
    result = _redact_processor(None, "info", event)
    assert result["card_no"] == REDACTED


@pytest.mark.unit
def test_redact_pin_partial():
    event = {"event": "punch", "pin": "10042"}
    result = _redact_processor(None, "info", event)
    assert result["pin"] == "10***"


@pytest.mark.unit
def test_redact_name():
    event = {"event": "sync", "name": "Rahul Kumar"}
    result = _redact_processor(None, "info", event)
    assert result["name"] == REDACTED


@pytest.mark.unit
def test_non_sensitive_fields_unchanged():
    event = {"event": "punch_received", "device_id": "abc-123", "count": 42}
    result = _redact_processor(None, "info", event)
    assert result["device_id"] == "abc-123"
    assert result["count"] == 42
