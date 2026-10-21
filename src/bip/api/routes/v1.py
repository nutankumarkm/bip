"""Consumer API v1 routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from bip.api.auth import TokenPayload, check_org_access, get_current_client, require_scope

router = APIRouter(prefix="/v1")


class OrgCreate(BaseModel):
    type: str
    name: str
    timezone: str = "Asia/Kolkata"
    retention_days: int = 730
    pin_range_start: int = 10001


class SiteCreate(BaseModel):
    name: str
    timezone: str = "Asia/Kolkata"
    active_hours: dict[str, list[str]] | None = None


class DeviceRegister(BaseModel):
    vendor: str
    family: str
    serial: str | None = None
    model: str | None = None
    mode: str = "push"
    site_id: str


class WebhookCreate(BaseModel):
    url: str
    events: list[str]


# --- In-memory stores for testing (production uses Postgres) ---

_orgs: dict[str, dict[str, Any]] = {}
_sites: dict[str, dict[str, Any]] = {}
_devices: dict[str, dict[str, Any]] = {}
_punches: list[dict[str, Any]] = []
_punch_seq = 0
_webhooks: dict[str, dict[str, Any]] = {}
_webhook_secrets: dict[str, str] = {}


def reset_stores() -> None:
    global _punch_seq
    _orgs.clear()
    _sites.clear()
    _devices.clear()
    _punches.clear()
    _punch_seq = 0
    _webhooks.clear()
    _webhook_secrets.clear()


def add_test_punch(org_id: str, site_id: str, device_id: str, pin: str, occurred_at: datetime, **kwargs: Any) -> int:
    global _punch_seq
    _punch_seq += 1
    punch = {
        "seq": _punch_seq,
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "site_id": site_id,
        "device_id": device_id,
        "device_pin": pin,
        "occurred_at": occurred_at.isoformat(),
        "verify_mode": kwargs.get("verify_mode", "fingerprint"),
        "source": kwargs.get("source", "adms"),
        "person_id": kwargs.get("person_id"),
        "received_at": datetime.now(UTC).isoformat(),
    }
    _punches.append(punch)
    return _punch_seq


# --- Org endpoints ---


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    client: TokenPayload = Depends(require_scope("orgs:write")),
) -> dict:
    org_id = str(uuid.uuid4())
    org = {
        "id": org_id,
        "partner_id": client.partner_id,
        "type": body.type,
        "name": body.name,
        "timezone": body.timezone,
        "retention_days": body.retention_days,
        "pin_range_start": body.pin_range_start,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _orgs[org_id] = org
    from bip.api.auth import register_org

    register_org(org_id, client.partner_id)
    return org


@router.get("/orgs/{org_id}")
async def get_org(
    org_id: str,
    client: TokenPayload = Depends(get_current_client),
) -> dict:
    check_org_access(org_id, client)
    org = _orgs.get(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


# --- Site endpoints ---


@router.post("/orgs/{org_id}/sites", status_code=status.HTTP_201_CREATED)
async def create_site(
    org_id: str,
    body: SiteCreate,
    client: TokenPayload = Depends(require_scope("orgs:write")),
) -> dict:
    check_org_access(org_id, client)
    site_id = str(uuid.uuid4())
    site = {
        "id": site_id,
        "org_id": org_id,
        "name": body.name,
        "timezone": body.timezone,
        "active_hours": body.active_hours,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _sites[site_id] = site
    return site


@router.get("/orgs/{org_id}/sites")
async def list_sites(
    org_id: str,
    client: TokenPayload = Depends(get_current_client),
) -> list[dict]:
    check_org_access(org_id, client)
    return [s for s in _sites.values() if s["org_id"] == org_id]


# --- Device endpoints ---


@router.post("/orgs/{org_id}/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    org_id: str,
    body: DeviceRegister,
    client: TokenPayload = Depends(require_scope("devices:write")),
) -> dict:
    check_org_access(org_id, client)
    device_id = str(uuid.uuid4())
    device = {
        "id": device_id,
        "org_id": org_id,
        "site_id": body.site_id,
        "vendor": body.vendor,
        "family": body.family,
        "serial": body.serial,
        "model": body.model,
        "mode": body.mode,
        "status": "expected",
        "created_at": datetime.now(UTC).isoformat(),
    }
    _devices[device_id] = device

    onboarding = {"device_id": device_id}
    if body.mode == "push":
        onboarding["instructions"] = "Configure device: Comm > ADMS/Cloud Server > Server address: <edge_host>:8081"
    elif body.mode == "gateway":
        onboarding["instructions"] = "Assign to a gateway; the gateway will discover the device on the LAN"

    return {**device, "onboarding": onboarding}


@router.get("/orgs/{org_id}/devices")
async def list_devices(
    org_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> list[dict]:
    check_org_access(org_id, client)
    return [d for d in _devices.values() if d["org_id"] == org_id]


@router.get("/orgs/{org_id}/devices/{device_id}")
async def get_device(
    org_id: str,
    device_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> dict:
    check_org_access(org_id, client)
    device = _devices.get(device_id)
    if not device or device["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


# --- Punch feed endpoint ---


@router.get("/orgs/{org_id}/punches")
async def list_punches(
    org_id: str,
    cursor: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    site_id: str | None = Query(None),
    client: TokenPayload = Depends(require_scope("punches:read")),
) -> dict:
    check_org_access(org_id, client)
    org_punches = [p for p in _punches if p["org_id"] == org_id and p["seq"] > cursor]
    if site_id:
        org_punches = [p for p in org_punches if p["site_id"] == site_id]
    org_punches.sort(key=lambda p: p["seq"])
    page = org_punches[:limit]
    next_cursor = page[-1]["seq"] if page else cursor
    return {"items": page, "next_cursor": next_cursor}


# --- Unmapped PINs ---


@router.get("/orgs/{org_id}/unmapped-pins")
async def unmapped_pins(
    org_id: str,
    client: TokenPayload = Depends(require_scope("punches:read")),
) -> list[dict]:
    check_org_access(org_id, client)
    unmapped = [p for p in _punches if p["org_id"] == org_id and p.get("person_id") is None]
    pins = {}
    for p in unmapped:
        pin = p["device_pin"]
        if pin not in pins:
            pins[pin] = {"device_pin": pin, "first_seen": p["occurred_at"], "count": 0}
        pins[pin]["count"] += 1
    return list(pins.values())


# --- Webhook endpoints ---


@router.post("/orgs/{org_id}/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    org_id: str,
    body: WebhookCreate,
    client: TokenPayload = Depends(require_scope("webhooks:write")),
) -> dict:
    check_org_access(org_id, client)
    wh_id = str(uuid.uuid4())
    import secrets

    secret = secrets.token_urlsafe(32)
    webhook = {
        "id": wh_id,
        "org_id": org_id,
        "url": body.url,
        "events": body.events,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _webhooks[wh_id] = webhook
    _webhook_secrets[wh_id] = secret
    return {**webhook, "secret": secret}


@router.get("/orgs/{org_id}/webhooks")
async def list_webhooks(
    org_id: str,
    client: TokenPayload = Depends(require_scope("webhooks:write")),
) -> list[dict]:
    check_org_access(org_id, client)
    return [w for w in _webhooks.values() if w["org_id"] == org_id]


@router.delete("/orgs/{org_id}/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    org_id: str,
    webhook_id: str,
    client: TokenPayload = Depends(require_scope("webhooks:write")),
) -> None:
    check_org_access(org_id, client)
    if webhook_id not in _webhooks or _webhooks[webhook_id]["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    del _webhooks[webhook_id]
    _webhook_secrets.pop(webhook_id, None)
