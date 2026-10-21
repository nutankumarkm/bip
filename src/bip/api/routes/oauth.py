"""OAuth2 token endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, status

from bip.api.auth import authenticate_client, create_access_token

router = APIRouter()


@router.post("/oauth/token")
async def token(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
) -> dict:
    if grant_type != "client_credentials":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant type")

    client = authenticate_client(client_id, client_secret)
    if client is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client credentials")

    access_token = create_access_token(client)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
    }
