"""Org Portal authentication — per-org login scoped to a single organisation."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_PORTAL_USERS: dict[str, dict[str, Any]] = {}   # email -> user record
_PORTAL_SESSIONS: dict[str, dict[str, Any]] = {}  # token -> session

PORTAL_SESSION_COOKIE = "bip_portal_session"


# ---------------------------------------------------------------------------
# Password helpers (PBKDF2-HMAC-SHA256, same approach as ops console)
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk_hex = stored.split("$", 1)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


def create_portal_user(
    email: str,
    password: str,
    org_id: str,
    display_name: str = "",
    role: str = "admin",
) -> dict[str, Any]:
    user: dict[str, Any] = {
        "email": email,
        "password_hash": _hash_password(password),
        "org_id": org_id,
        "display_name": display_name or email.split("@")[0].title(),
        "role": role,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _PORTAL_USERS[email.lower()] = user
    return user


def get_portal_user(email: str) -> dict[str, Any] | None:
    return _PORTAL_USERS.get(email.lower())


def list_portal_users(org_id: str | None = None) -> list[dict[str, Any]]:
    users = list(_PORTAL_USERS.values())
    if org_id:
        users = [u for u in users if u["org_id"] == org_id]
    return users


def authenticate_portal_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_portal_user(email)
    if user and _verify_password(password, user["password_hash"]):
        return user
    return None


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def create_portal_session(email: str, org_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _PORTAL_SESSIONS[token] = {
        "email": email,
        "org_id": org_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return token


def get_portal_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return _PORTAL_SESSIONS.get(token)


def delete_portal_session(token: str | None) -> None:
    if token and token in _PORTAL_SESSIONS:
        del _PORTAL_SESSIONS[token]


def clear_portal_state() -> None:
    _PORTAL_USERS.clear()
    _PORTAL_SESSIONS.clear()
