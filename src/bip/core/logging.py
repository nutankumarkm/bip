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
    }
)

_PIN_PATTERN = re.compile(r"\b\d{4,8}\b")


def _redact_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        elif key == "pin" and isinstance(value, str) and len(value) > 2:
            event_dict[key] = value[:2] + "***"
        elif key == "name" and isinstance(value, str):
            event_dict[key] = REDACTED
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
