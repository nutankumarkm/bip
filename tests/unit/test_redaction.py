"""Unit tests verifying sensitive data redaction in logging (M9)."""

from __future__ import annotations

from bip.core.logging import REDACTED, _redact_processor


def test_top_level_sensitive_keys_redacted() -> None:
    sensitive_keys = [
        "password",
        "secret",
        "token",
        "card_no",
        "card_number",
        "ciphertext",
        "template",
        "tmp",
        "totp_secret",
        "secret_hash",
        "credential_ciphertext",
        "private_key",
        "authorization",
        "cookie",
        "credential",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "biometric_data",
        "fingerprint",
        "face_template",
    ]
    for key in sensitive_keys:
        event = {"event": "test_event", key: "super_secret_value"}
        result = _redact_processor(None, "info", event)
        assert result[key] == REDACTED, f"Key {key} was not redacted"


def test_nested_dictionary_redaction() -> None:
    event = {
        "event": "device_handshake",
        "device_id": "dev_001",
        "device_config": {
            "api_key": "raw_api_key_12345",
            "password": "device_master_pw",
            "info": {
                "token": "nested_bearer_token",
                "vendor": "ZKTeco",
            },
        },
    }
    result = _redact_processor(None, "info", event)
    assert result["device_id"] == "dev_001"
    assert result["device_config"]["api_key"] == REDACTED
    assert result["device_config"]["password"] == REDACTED
    assert result["device_config"]["info"]["token"] == REDACTED
    assert result["device_config"]["info"]["vendor"] == "ZKTeco"


def test_nested_list_redaction() -> None:
    event = {
        "event": "batch_upload",
        "items": [
            {"password": "secret1", "id": 1},
            {"token": "secret2", "id": 2},
        ],
    }
    result = _redact_processor(None, "info", event)
    assert result["items"][0]["password"] == REDACTED
    assert result["items"][0]["id"] == 1
    assert result["items"][1]["token"] == REDACTED
    assert result["items"][1]["id"] == 2


def test_pin_masking() -> None:
    event = {"event": "punch_logged", "pin": "10045"}
    result = _redact_processor(None, "info", event)
    assert result["pin"] == "10***"


def test_person_name_redacted() -> None:
    event = {"event": "person_enrolled", "name": "Rajesh Kumar", "person_id": "p_123"}
    result = _redact_processor(None, "info", event)
    assert result["name"] == REDACTED
    assert result["person_id"] == "p_123"


def test_safe_operational_fields_preserved() -> None:
    event = {
        "event": "punch_ingested",
        "org_id": "org_abc",
        "site_id": "site_xyz",
        "device_id": "dev_99",
        "status": "success",
        "count": 42,
    }
    result = _redact_processor(None, "info", event.copy())
    for k, v in event.items():
        assert result[k] == v
