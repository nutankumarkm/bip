"""OAuth2 client credentials and JWT token handling."""

from __future__ import annotations

import hashlib
import time
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from bip.core.settings import settings

security = HTTPBearer()


class TokenPayload(BaseModel):
    sub: str
    partner_id: str
    scopes: list[str]
    exp: int


class ApiClientInfo(BaseModel):
    client_id: str
    partner_id: str
    scopes: list[str]


_clients_store: dict[str, dict[str, Any]] = {}


def register_client(client_id: str, secret: str, partner_id: str, scopes: list[str]) -> None:
    _clients_store[client_id] = {
        "client_id": client_id,
        "secret_hash": hashlib.sha256(secret.encode()).hexdigest(),
        "partner_id": partner_id,
        "scopes": scopes,
        "active": True,
    }


def clear_clients() -> None:
    _clients_store.clear()


def authenticate_client(client_id: str, client_secret: str) -> dict[str, Any] | None:
    client = _clients_store.get(client_id)
    if not client or not client["active"]:
        return None
    expected = client["secret_hash"]
    actual = hashlib.sha256(client_secret.encode()).hexdigest()
    if actual != expected:
        return None
    return client


def create_access_token(client: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "sub": client["client_id"],
        "partner_id": client["partner_id"],
        "scopes": client["scopes"],
        "exp": now + settings.jwt_expiry_minutes * 60,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**data)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e


def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    return decode_token(credentials.credentials)


def require_scope(scope: str):
    def checker(client: TokenPayload = Depends(get_current_client)) -> TokenPayload:
        if scope not in client.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing scope: {scope}")
        return client

    return checker


_org_partner_map: dict[str, str] = {}


def register_org(org_id: str, partner_id: str) -> None:
    _org_partner_map[org_id] = partner_id


def clear_orgs() -> None:
    _org_partner_map.clear()


def check_org_access(org_id: str, client: TokenPayload) -> None:
    partner = _org_partner_map.get(org_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if partner != client.partner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this organization")
