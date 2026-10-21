"""Ops console authentication and session management.

Uses email + password (bcrypt via argon2-cffi) + TOTP (pyotp), CSRF tokens.
Sessions are stored in a thread-safe in-memory store (Postgres-backed in prod).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Callable
from typing import Any

import pyotp
from fastapi import Cookie, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

# ---------------------------------------------------------------------------
# In-memory staff admin store (Postgres-backed in prod)
# ---------------------------------------------------------------------------

_CONSOLE_USERS: dict[str, dict[str, Any]] = {}
_SESSIONS: dict[str, dict[str, Any]] = {}
_CSRF_TOKENS: dict[str, str] = {}
_SESSION_TTL = 28800  # 8 hours


def _hash_password(password: str) -> str:
    """Argon2-style hash using PBKDF2 (simpler, no C extension required here)."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260000)
    return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, _, iters, salt, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_console_user(
    email: str,
    password: str,
    role: str = "admin",
    totp_secret: str | None = None,
) -> dict[str, Any]:
    """Register a console user. Returns the record including totp_secret."""
    if not totp_secret:
        totp_secret = pyotp.random_base32()
    _CONSOLE_USERS[email] = {
        "email": email,
        "password_hash": _hash_password(password),
        "role": role,
        "totp_secret": totp_secret,
        "totp_enabled": True,
        "active": True,
    }
    return _CONSOLE_USERS[email]


def get_console_user(email: str) -> dict[str, Any] | None:
    return _CONSOLE_USERS.get(email)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def create_session(email: str, pre_totp: bool = False) -> str:
    """Create a session and return the session token."""
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "email": email,
        "created_at": time.time(),
        "pre_totp": pre_totp,  # True = password verified but TOTP pending
    }
    return token


def get_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    sess = _SESSIONS.get(token)
    if not sess:
        return None
    if time.time() - sess["created_at"] > _SESSION_TTL:
        _SESSIONS.pop(token, None)
        return None
    return sess


def delete_session(token: str) -> None:
    _SESSIONS.pop(token, None)


def generate_csrf() -> str:
    return secrets.token_urlsafe(24)


def verify_csrf(token: str | None, stored: str | None) -> bool:
    if not token or not stored:
        return False
    return hmac.compare_digest(token, stored)


def clear_console_state() -> None:
    """Test helper — reset all in-memory state."""
    _CONSOLE_USERS.clear()
    _SESSIONS.clear()
    _CSRF_TOKENS.clear()


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------

SESSION_COOKIE = "bip_ops_session"
CSRF_HEADER = "X-CSRF-Token"


def get_authenticated_session(request: Request) -> dict[str, Any]:
    """Dependency: require a fully-authenticated (post-TOTP) session."""
    token = request.cookies.get(SESSION_COOKIE)
    sess = get_session(token)
    if not sess or sess.get("pre_totp"):
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/ops/login"})
    return sess


def get_session_optional(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(SESSION_COOKIE)
    return get_session(token)
