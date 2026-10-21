"""BIP API client with token caching."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx


class BIPClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expires: float = 0
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires - 30:
            return self._token
        resp = self._http.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 900)
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._ensure_token()}"}

    def get_org(self, org_id: str) -> dict[str, Any]:
        resp = self._http.get(f"/v1/orgs/{org_id}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def iter_punches(self, org_id: str, cursor: int = 0, limit: int = 100) -> Iterator[dict[str, Any]]:
        while True:
            resp = self._http.get(
                f"/v1/orgs/{org_id}/punches",
                params={"cursor": cursor, "limit": limit},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            yield from items
            next_cursor = data.get("next_cursor", cursor)
            if next_cursor == cursor:
                break
            cursor = next_cursor

    def upsert_person(self, org_id: str, external_ref: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = self._http.put(
            f"/v1/orgs/{org_id}/people/{external_ref}",
            json=body,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def delete_person(self, org_id: str, external_ref: str) -> None:
        resp = self._http.delete(
            f"/v1/orgs/{org_id}/people/{external_ref}",
            headers=self._headers(),
        )
        resp.raise_for_status()

    def list_people(self, org_id: str, active: bool | None = None, site_id: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if active is not None:
            params["active"] = str(active).lower()
        if site_id:
            params["site_id"] = site_id
        resp = self._http.get(f"/v1/orgs/{org_id}/people", params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_person(self, org_id: str, external_ref: str) -> dict[str, Any]:
        resp = self._http.get(f"/v1/orgs/{org_id}/people/{external_ref}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def create_command(
        self, org_id: str, device_id: str, cmd_type: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"device_id": device_id, "type": cmd_type}
        if params:
            body["params"] = params
        resp = self._http.post(f"/v1/orgs/{org_id}/commands", json=body, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def list_commands(
        self, org_id: str, device_id: str | None = None, state: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if device_id:
            params["device_id"] = device_id
        if state:
            params["state"] = state
        resp = self._http.get(f"/v1/orgs/{org_id}/commands", params=params, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def get_match_suggestions(self, org_id: str) -> list[dict[str, Any]]:
        resp = self._http.get(f"/v1/orgs/{org_id}/match-suggestions", headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def reconcile(self, org_id: str, device_id: str) -> dict[str, Any]:
        resp = self._http.post(f"/v1/orgs/{org_id}/reconcile", json={"device_id": device_id}, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()


class LocalFeedClient:
    def __init__(self, base_url: str = "http://127.0.0.1:47800", token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(base_url=self.base_url, timeout=10.0)

    def iter_punches(self, cursor: int = 0, limit: int = 100) -> Iterator[dict[str, Any]]:
        while True:
            headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
            resp = self._http.get(
                "/v1/punches",
                params={"cursor": cursor, "limit": limit},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            yield from items
            next_cursor = data.get("next_cursor", cursor)
            if next_cursor == cursor:
                break
            cursor = next_cursor

    def close(self) -> None:
        self._http.close()
