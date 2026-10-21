"""Consumer API v1 routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from bip.api.auth import TokenPayload, check_org_access, get_current_client, require_scope

router = APIRouter(prefix="/v1")


# --- Request / response models ---


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


class PersonUpsert(BaseModel):
    person_type: str = "student"
    display_name: str
    active: bool = True
    site_ids: list[str] = Field(default_factory=list)
    card_no: str | None = None


class CommandCreate(BaseModel):
    device_id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ReconcileRequest(BaseModel):
    device_id: str


class MatchSuggestion(BaseModel):
    device_pin: str
    person_id: str
    person_name: str
    score: float
    reason: str


# --- In-memory stores for testing (production uses Postgres) ---

_orgs: dict[str, dict[str, Any]] = {}
_sites: dict[str, dict[str, Any]] = {}
_devices: dict[str, dict[str, Any]] = {}
_punches: list[dict[str, Any]] = []
_punch_seq = 0
_webhooks: dict[str, dict[str, Any]] = {}
_webhook_secrets: dict[str, str] = {}
_people: dict[str, dict[str, Any]] = {}
_person_identities: dict[str, dict[str, Any]] = {}
_enrolments: dict[str, dict[str, Any]] = {}
_commands: dict[str, dict[str, Any]] = {}
_command_seq = 0
_pin_counters: dict[str, int] = {}


def reset_stores() -> None:
    global _punch_seq, _command_seq
    _orgs.clear()
    _sites.clear()
    _devices.clear()
    _punches.clear()
    _punch_seq = 0
    _webhooks.clear()
    _webhook_secrets.clear()
    _people.clear()
    _person_identities.clear()
    _enrolments.clear()
    _commands.clear()
    _command_seq = 0
    _pin_counters.clear()


def add_test_enrolment(person_id: str, device_id: str, **kwargs: Any) -> dict[str, Any]:
    key = f"{person_id}:{device_id}"
    enrolment = {
        "person_id": person_id,
        "device_id": device_id,
        "fingerprints": kwargs.get("fingerprints", 0),
        "face": kwargs.get("face", False),
        "palm": kwargs.get("palm", False),
        "card": kwargs.get("card", False),
        "synced_at": kwargs.get("synced_at"),
    }
    _enrolments[key] = enrolment
    return enrolment


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


# --- PIN allocation helper ---


def _allocate_pin(org_id: str) -> str:
    org = _orgs.get(org_id)
    start = org.get("pin_range_start", 10001) if org else 10001
    if org_id not in _pin_counters:
        existing = [
            int(ident["device_pin"])
            for ident in _person_identities.values()
            if ident["org_id"] == org_id and ident["device_pin"].isdigit()
        ]
        _pin_counters[org_id] = max(existing) + 1 if existing else start
    pin = str(_pin_counters[org_id])
    _pin_counters[org_id] += 1
    return pin


# --- Command fan-out helper ---


def _fan_out_person_to_devices(org_id: str, person_id: str, pin: str, display_name: str, card_no: str | None) -> int:
    global _command_seq
    site_ids = set()
    person = _people.get(person_id, {})
    for sid in person.get("site_ids", []):
        site_ids.add(sid)

    target_devices = [d for d in _devices.values() if d["org_id"] == org_id and d.get("site_id") in site_ids]

    count = 0
    for dev in target_devices:
        _command_seq += 1
        cmd_id = str(uuid.uuid4())
        _commands[cmd_id] = {
            "id": cmd_id,
            "org_id": org_id,
            "device_id": dev["id"],
            "cmd_no": _command_seq,
            "type": "set_user",
            "params": {"pin": pin, "name": display_name, "card_no": card_no or ""},
            "state": "queued",
            "attempts": 0,
            "idempotency_key": f"sync-person-{person_id}-{dev['id']}",
            "requested_by": "system",
            "created_at": datetime.now(UTC).isoformat(),
        }
        count += 1
    return count


def _fan_out_delete_person(org_id: str, pin: str, site_ids: list[str]) -> int:
    global _command_seq
    target_devices = [d for d in _devices.values() if d["org_id"] == org_id and d.get("site_id") in site_ids]

    count = 0
    for dev in target_devices:
        _command_seq += 1
        cmd_id = str(uuid.uuid4())
        _commands[cmd_id] = {
            "id": cmd_id,
            "org_id": org_id,
            "device_id": dev["id"],
            "cmd_no": _command_seq,
            "type": "delete_user",
            "params": {"pin": pin},
            "state": "queued",
            "attempts": 0,
            "idempotency_key": f"delete-pin-{pin}-{dev['id']}",
            "requested_by": "system",
            "created_at": datetime.now(UTC).isoformat(),
        }
        count += 1
    return count


# --- People endpoints ---


@router.put("/orgs/{org_id}/people/{external_ref}", status_code=status.HTTP_200_OK)
async def upsert_person(
    org_id: str,
    external_ref: str,
    body: PersonUpsert,
    client: TokenPayload = Depends(require_scope("people:write")),
) -> dict:
    check_org_access(org_id, client)

    existing = None
    for p in _people.values():
        if p["org_id"] == org_id and p["external_ref"] == external_ref:
            existing = p
            break

    if existing:
        existing["display_name"] = body.display_name
        existing["person_type"] = body.person_type
        existing["active"] = body.active
        existing["site_ids"] = body.site_ids
        existing["updated_at"] = datetime.now(UTC).isoformat()
        person_id = existing["id"]

        ident = _person_identities.get(person_id)
        if ident and body.card_no is not None:
            ident["card_no"] = body.card_no

        pin = ident["device_pin"] if ident else ""
        _fan_out_person_to_devices(org_id, person_id, pin, body.display_name, body.card_no)

        result = {**existing}
        if ident:
            result["device_pin"] = ident["device_pin"]
            result["card_no"] = ident.get("card_no")
        return result

    person_id = str(uuid.uuid4())
    person = {
        "id": person_id,
        "org_id": org_id,
        "external_ref": external_ref,
        "person_type": body.person_type,
        "display_name": body.display_name,
        "active": body.active,
        "site_ids": body.site_ids,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _people[person_id] = person

    pin = _allocate_pin(org_id)
    ident = {
        "id": str(uuid.uuid4()),
        "person_id": person_id,
        "org_id": org_id,
        "device_pin": pin,
        "card_no": body.card_no,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _person_identities[person_id] = ident

    _fan_out_person_to_devices(org_id, person_id, pin, body.display_name, body.card_no)

    return {**person, "device_pin": pin, "card_no": body.card_no}


@router.get("/orgs/{org_id}/people")
async def list_people(
    org_id: str,
    active: bool | None = Query(None),
    site_id: str | None = Query(None),
    client: TokenPayload = Depends(require_scope("people:write")),
) -> list[dict]:
    check_org_access(org_id, client)
    result = []
    for p in _people.values():
        if p["org_id"] != org_id:
            continue
        if active is not None and p["active"] != active:
            continue
        if site_id is not None and site_id not in p.get("site_ids", []):
            continue
        entry = {**p}
        ident = _person_identities.get(p["id"])
        if ident:
            entry["device_pin"] = ident["device_pin"]
            entry["card_no"] = ident.get("card_no")
        result.append(entry)
    return result


@router.get("/orgs/{org_id}/people/{external_ref}")
async def get_person(
    org_id: str,
    external_ref: str,
    client: TokenPayload = Depends(require_scope("people:write")),
) -> dict:
    check_org_access(org_id, client)
    for p in _people.values():
        if p["org_id"] == org_id and p["external_ref"] == external_ref:
            entry = {**p}
            ident = _person_identities.get(p["id"])
            if ident:
                entry["device_pin"] = ident["device_pin"]
                entry["card_no"] = ident.get("card_no")
            return entry
    raise HTTPException(status_code=404, detail="Person not found")


@router.delete("/orgs/{org_id}/people/{external_ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person(
    org_id: str,
    external_ref: str,
    client: TokenPayload = Depends(require_scope("people:write")),
) -> None:
    check_org_access(org_id, client)
    person_id = None
    for pid, p in _people.items():
        if p["org_id"] == org_id and p["external_ref"] == external_ref:
            person_id = pid
            break
    if person_id is None:
        raise HTTPException(status_code=404, detail="Person not found")

    person = _people[person_id]
    ident = _person_identities.get(person_id)
    pin = ident["device_pin"] if ident else None

    if pin:
        _fan_out_delete_person(org_id, pin, person.get("site_ids", []))

    del _people[person_id]
    _person_identities.pop(person_id, None)
    for key in [k for k, e in _enrolments.items() if e["person_id"] == person_id]:
        del _enrolments[key]


# --- Enrolment endpoints ---


@router.get("/orgs/{org_id}/people/{external_ref}/enrolments")
async def list_person_enrolments(
    org_id: str,
    external_ref: str,
    client: TokenPayload = Depends(require_scope("people:write")),
) -> list[dict]:
    check_org_access(org_id, client)
    person = None
    for p in _people.values():
        if p["org_id"] == org_id and p["external_ref"] == external_ref:
            person = p
            break
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return [e for e in _enrolments.values() if e["person_id"] == person["id"]]


@router.get("/orgs/{org_id}/devices/{device_id}/enrolments")
async def list_device_enrolments(
    org_id: str,
    device_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> list[dict]:
    check_org_access(org_id, client)
    device = _devices.get(device_id)
    if not device or device["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Device not found")
    return [e for e in _enrolments.values() if e["device_id"] == device_id]


# --- Command endpoints ---


@router.post("/orgs/{org_id}/commands", status_code=status.HTTP_201_CREATED)
async def create_command(
    org_id: str,
    body: CommandCreate,
    client: TokenPayload = Depends(require_scope("commands:write")),
) -> dict:
    global _command_seq
    check_org_access(org_id, client)

    device = _devices.get(body.device_id)
    if not device or device["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Device not found")

    idem_key = body.idempotency_key or str(uuid.uuid4())
    for cmd in _commands.values():
        if cmd["idempotency_key"] == idem_key and cmd["org_id"] == org_id:
            return cmd

    _command_seq += 1
    cmd_id = str(uuid.uuid4())
    command = {
        "id": cmd_id,
        "org_id": org_id,
        "device_id": body.device_id,
        "cmd_no": _command_seq,
        "type": body.type,
        "params": body.params,
        "state": "queued",
        "attempts": 0,
        "idempotency_key": idem_key,
        "requested_by": client.sub,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _commands[cmd_id] = command
    return command


@router.get("/orgs/{org_id}/commands")
async def list_commands(
    org_id: str,
    device_id: str | None = Query(None),
    state: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    client: TokenPayload = Depends(require_scope("commands:write")),
) -> list[dict]:
    check_org_access(org_id, client)
    result = []
    for cmd in _commands.values():
        if cmd["org_id"] != org_id:
            continue
        if device_id and cmd["device_id"] != device_id:
            continue
        if state and cmd["state"] != state:
            continue
        result.append(cmd)
    result.sort(key=lambda c: c["cmd_no"])
    return result[:limit]


@router.get("/orgs/{org_id}/commands/{command_id}")
async def get_command(
    org_id: str,
    command_id: str,
    client: TokenPayload = Depends(require_scope("commands:write")),
) -> dict:
    check_org_access(org_id, client)
    cmd = _commands.get(command_id)
    if not cmd or cmd["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Command not found")
    return cmd


# --- Match suggestions endpoint ---


@router.get("/orgs/{org_id}/match-suggestions")
async def match_suggestions(
    org_id: str,
    client: TokenPayload = Depends(require_scope("people:write")),
) -> list[dict]:
    check_org_access(org_id, client)

    unmapped = {}
    for p in _punches:
        if p["org_id"] != org_id or p.get("person_id") is not None:
            continue
        pin = p["device_pin"]
        if pin not in unmapped:
            unmapped[pin] = {"device_pin": pin, "count": 0, "first_seen": p["occurred_at"]}
        unmapped[pin]["count"] += 1

    if not unmapped:
        return []

    try:
        from rapidfuzz import fuzz
    except ImportError:
        return []

    org_people = [p for p in _people.values() if p["org_id"] == org_id]
    suggestions = []
    for pin_info in unmapped.values():
        pin = pin_info["device_pin"]
        best_score = 0.0
        best_person = None
        for person in org_people:
            name: str = person.get("display_name", "")
            score = fuzz.ratio(pin, name) / 100.0
            ident = _person_identities.get(person["id"])
            if ident and ident["device_pin"] == pin:
                score = 1.0
            if score > best_score:
                best_score = score
                best_person = person
        if best_person and best_score > 0.3:
            suggestions.append(
                {
                    "device_pin": pin,
                    "person_id": best_person["id"],
                    "person_name": best_person["display_name"],
                    "score": round(best_score, 3),
                    "reason": "pin_match" if best_score == 1.0 else "name_similarity",
                    "punch_count": pin_info["count"],
                }
            )

    suggestions.sort(key=lambda s: (-float(s["score"]), -int(s["punch_count"])))
    return suggestions


# --- Reconciliation endpoint ---


@router.post("/orgs/{org_id}/reconcile")
async def reconcile(
    org_id: str,
    body: ReconcileRequest,
    client: TokenPayload = Depends(require_scope("devices:write")),
) -> dict:
    check_org_access(org_id, client)

    device = _devices.get(body.device_id)
    if not device or device["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Device not found")

    device_site = device.get("site_id")
    expected_people = []
    for p in _people.values():
        if p["org_id"] == org_id and p["active"] and device_site in p.get("site_ids", []):
            ident = _person_identities.get(p["id"])
            if ident:
                expected_people.append({"person_id": p["id"], "pin": ident["device_pin"], "name": p["display_name"]})

    device_enrolments = {e["person_id"]: e for e in _enrolments.values() if e["device_id"] == body.device_id}

    expected_ids = {ep["person_id"] for ep in expected_people}
    enrolled_ids = set(device_enrolments.keys())

    missing = expected_ids - enrolled_ids
    extra = enrolled_ids - expected_ids

    return {
        "device_id": body.device_id,
        "expected_count": len(expected_ids),
        "enrolled_count": len(enrolled_ids),
        "missing": [ep for ep in expected_people if ep["person_id"] in missing],
        "extra": [{"person_id": pid} for pid in extra],
        "in_sync": len(missing) == 0 and len(extra) == 0,
    }
