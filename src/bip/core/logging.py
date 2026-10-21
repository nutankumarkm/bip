"""Structured logging with redaction of sensitive fields."""

from __future__ import annotations

import re
from typing import Any

import structlog

REDACTED = "***REDACTED***"

_SENSITIVE_KEYS = frozenset(
    {
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
        "credentials",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "biometric_data",
        "fingerprint",
        "face_template",
    }
)

_PIN_PATTERN = re.compile(r"\b\d{4,8}\b")


def _redact_value(val: Any) -> Any:
    if isinstance(val, dict):
        res: dict[str, Any] = {}
        for k, v in val.items():
            if k.lower() in _SENSITIVE_KEYS:
                res[k] = REDACTED
            elif k == "pin" and isinstance(v, str) and len(v) > 2:
                res[k] = v[:2] + "***"
            elif k == "name" and isinstance(v, str):
                res[k] = REDACTED
            else:
                res[k] = _redact_value(v)
        return res
    if isinstance(val, list):
        return [_redact_value(item) for item in val]
    return val


def _redact_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        elif key == "pin" and isinstance(value, str) and len(value) > 2:
            event_dict[key] = value[:2] + "***"
        elif key == "name" and isinstance(value, str):
            event_dict[key] = REDACTED
        elif isinstance(value, (dict, list)):
            event_dict[key] = _redact_value(value)
    return event_dict


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if log_format == "console":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
