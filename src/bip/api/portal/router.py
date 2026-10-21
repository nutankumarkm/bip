"""Org Portal — per-organisation self-service web console."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bip.api.portal.auth import (
    PORTAL_SESSION_COOKIE,
    authenticate_portal_user,
    create_portal_session,
    delete_portal_session,
    get_portal_session,
)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(prefix="/portal", tags=["portal"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render(request: Request, name: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)


def _require_session(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(PORTAL_SESSION_COOKIE)
    return get_portal_session(token)


def _org_context(sess: dict[str, Any]) -> dict[str, Any]:
    """Pull live data for this org from the shared in-memory stores."""
    from bip.api.routes.v1 import _devices, _orgs, _people, _punches, _sites

    org_id = sess["org_id"]
    org = _orgs.get(org_id, {"id": org_id, "name": "My Organisation"})
    sites = [s for s in _sites.values() if s.get("org_id") == org_id]
    site_ids = {s["id"] for s in sites}
    devices = [d for d in _devices.values() if d.get("org_id") == org_id]
    punches = [p for p in _punches if p.get("org_id") == org_id]
    people = [p for p in _people.values() if p.get("org_id") == org_id]

    from datetime import UTC, datetime
    today_str = datetime.now(UTC).date().isoformat()
    today_punches = [p for p in punches if p.get("occurred_at", "")[:10] == today_str]

    return {
        "org": org,
        "sites": sites,
        "site_ids": site_ids,
        "devices": devices,
        "punches": punches,
        "people": people,
        "today_punches": today_punches,
    }


def _ctx(request: Request, sess: dict[str, Any], active_page: str, **extra: Any) -> dict[str, Any]:
    return {"request": request, "sess": sess, "active_page": active_page, **extra}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def portal_login_get(request: Request, error: str = "") -> HTMLResponse:
    return _render(request, "portal_login.html", {"request": request, "error": error})


@router.post("/login")
async def portal_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> Any:
    user = authenticate_portal_user(email, password)
    if not user:
        return _render(
            request,
            "portal_login.html",
            {"request": request, "error": "Invalid email or password.", "email": email},
            status_code=401,
        )
    token = create_portal_session(user["email"], user["org_id"])
    resp = RedirectResponse(url="/portal/", status_code=303)
    resp.set_cookie(PORTAL_SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=28800)
    return resp


@router.get("/logout")
async def portal_logout(request: Request) -> RedirectResponse:
    token = request.cookies.get(PORTAL_SESSION_COOKIE)
    delete_portal_session(token)
    resp = RedirectResponse("/portal/login", status_code=303)
    resp.delete_cookie(PORTAL_SESSION_COOKIE)
    return resp


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def portal_dashboard(request: Request) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    data = _org_context(sess)
    all_pins = {p.get("device_pin") for p in data["punches"]}
    people_pins = {str(p.get("pin", "")) for p in data["people"]}
    unmapped = len(all_pins - people_pins)

    stats = {
        "sites": len(data["sites"]),
        "devices": len(data["devices"]),
        "people": len(data["people"]),
        "punches_today": len(data["today_punches"]),
        "total_punches": len(data["punches"]),
        "unmapped_pins": unmapped,
    }
    recent_punches = list(reversed(data["punches"]))[:8]
    return _render(
        request,
        "portal_dashboard.html",
        _ctx(request, sess, "dashboard", stats=stats, recent_punches=recent_punches, org=data["org"]),
    )


# ---------------------------------------------------------------------------
# Attendance Feed
# ---------------------------------------------------------------------------


@router.get("/attendance", response_class=HTMLResponse)
async def portal_attendance(
    request: Request,
    verify_mode: str = "",
    offset: int = 0,
    limit: int = 100,
) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    data = _org_context(sess)
    punches = list(reversed(data["punches"]))
    if verify_mode:
        punches = [p for p in punches if p.get("verify_mode") == verify_mode]

    from datetime import UTC, datetime
    today_str = datetime.now(UTC).date().isoformat()
    all_pins = {p.get("device_pin") for p in data["punches"]}
    people_pins = {str(p.get("pin", "")) for p in data["people"]}

    stats = {
        "total": len(data["punches"]),
        "today": len(data["today_punches"]),
        "unique_pins": len(all_pins),
        "active_devices": len({p.get("device_id") for p in data["punches"]}),
        "unmapped": len(all_pins - people_pins),
    }
    devices_by_id = {d["id"]: d for d in data["devices"]}

    return _render(
        request,
        "portal_attendance.html",
        _ctx(
            request, sess, "attendance",
            org=data["org"],
            punches=punches[offset: offset + limit],
            stats=stats,
            devices_by_id=devices_by_id,
            filters={"verify_mode": verify_mode},
            offset=offset,
            limit=limit,
        ),
    )


# ---------------------------------------------------------------------------
# People & Roster
# ---------------------------------------------------------------------------


@router.get("/people", response_class=HTMLResponse)
async def portal_people(request: Request, success: str = "", error: str = "") -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    data = _org_context(sess)
    punch_counts: dict[str, int] = {}
    for p in data["punches"]:
        pin = str(p.get("device_pin", ""))
        punch_counts[pin] = punch_counts.get(pin, 0) + 1

    people_enriched = [{**p, "punch_count": punch_counts.get(str(p.get("pin", "")), 0)} for p in data["people"]]
    people_pins = {str(p.get("pin", "")) for p in data["people"]}
    punch_pins = {str(p.get("device_pin", "")) for p in data["punches"]}
    unmapped_pins = sorted(punch_pins - people_pins)

    return _render(
        request,
        "portal_people.html",
        _ctx(
            request, sess, "people",
            org=data["org"],
            people=people_enriched,
            unmapped_pins=unmapped_pins,
            success=success,
            error=error,
        ),
    )


@router.post("/people")
async def portal_people_post(
    request: Request,
    display_name: str = Form(...),
    person_type: str = Form("student"),
    external_ref: str = Form(""),
    card_no: str = Form(""),
    manual_pin: str = Form(""),
) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    import uuid
    from datetime import UTC, datetime

    from bip.api.routes.v1 import _orgs, _people, _pin_counters

    org_id = sess["org_id"]
    if manual_pin.strip():
        pin = manual_pin.strip()
    else:
        org = _orgs.get(org_id, {})
        start = int(org.get("pin_range_start", 10001))
        current = _pin_counters.get(org_id, start - 1)
        pin = str(current + 1)
        _pin_counters[org_id] = current + 1

    person_id = str(uuid.uuid4())
    _people[person_id] = {
        "id": person_id,
        "org_id": org_id,
        "person_type": person_type,
        "display_name": display_name.strip(),
        "pin": pin,
        "external_ref": external_ref.strip() or None,
        "card_no": card_no.strip() or None,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return RedirectResponse(f"/portal/people?success=Added+'{display_name}'+with+PIN+{pin}", status_code=303)


# ---------------------------------------------------------------------------
# Devices  (self-serve registration)
# ---------------------------------------------------------------------------


@router.get("/devices", response_class=HTMLResponse)
async def portal_devices(request: Request, success: str = "", error: str = "") -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    data = _org_context(sess)
    punch_counts: dict[str, int] = {}
    for p in data["punches"]:
        did = str(p.get("device_id", ""))
        punch_counts[did] = punch_counts.get(did, 0) + 1

    sites_by_id = {s["id"]: s for s in data["sites"]}
    devices_enriched = [
        {**d, "punch_count": punch_counts.get(d["id"], 0), "site_name": sites_by_id.get(d.get("site_id", ""), {}).get("name", "—")}
        for d in data["devices"]
    ]

    # Get server host for setup instructions
    host = request.headers.get("host", "your-server.example.com").split(":")[0]

    return _render(
        request,
        "portal_devices.html",
        _ctx(
            request, sess, "devices",
            org=data["org"],
            devices=devices_enriched,
            sites=data["sites"],
            server_host=host,
            success=success,
            error=error,
        ),
    )


@router.post("/devices")
async def portal_devices_post(
    request: Request,
    serial: str = Form(...),
    label: str = Form(...),
    family: str = Form("zk_adms"),
    site_id: str = Form(""),
) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    import uuid
    from datetime import UTC, datetime

    from bip.api.routes.v1 import _devices, _sites

    org_id = sess["org_id"]
    serial_clean = serial.strip().upper()
    label_clean = label.strip()

    # If no site chosen, use first site for this org or leave blank
    if not site_id:
        org_sites = [s for s in _sites.values() if s.get("org_id") == org_id]
        site_id = org_sites[0]["id"] if org_sites else ""

    did = str(uuid.uuid4())
    _devices[did] = {
        "id": did,
        "serial": serial_clean,
        "serial_number": serial_clean,
        "label": label_clean,
        "name": label_clean,
        "family": family,
        "vendor": family.split("_")[0] if "_" in family else family,
        "model": family,
        "site_id": site_id,
        "org_id": org_id,
        "mode": "push",
        "status": "ready",
        "is_active": True,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }

    # Whitelist in edge store so push traffic is immediately accepted
    try:
        from bip.edge.adms import _store
        await _store.register_device(serial_clean, {"id": did, "status": "active", "serial": serial_clean})
    except Exception:
        pass

    return RedirectResponse(
        f"/portal/devices?success=Machine+'{label_clean}'+({serial_clean})+registered!+See+setup+instructions+below.",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Sites  (self-serve creation)
# ---------------------------------------------------------------------------


@router.get("/sites", response_class=HTMLResponse)
async def portal_sites(request: Request, success: str = "", error: str = "") -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    data = _org_context(sess)
    device_counts: dict[str, int] = {}
    for d in data["devices"]:
        sid = d.get("site_id", "")
        device_counts[sid] = device_counts.get(sid, 0) + 1

    sites_enriched = [{**s, "device_count": device_counts.get(s["id"], 0)} for s in data["sites"]]

    return _render(
        request,
        "portal_sites.html",
        _ctx(request, sess, "sites", org=data["org"], sites=sites_enriched, success=success, error=error),
    )


@router.post("/sites")
async def portal_sites_post(
    request: Request,
    name: str = Form(...),
    address: str = Form(""),
    timezone: str = Form("Asia/Kolkata"),
) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    import uuid
    from datetime import UTC, datetime

    from bip.api.routes.v1 import _sites

    sid = str(uuid.uuid4())
    _sites[sid] = {
        "id": sid,
        "org_id": sess["org_id"],
        "name": name.strip(),
        "address": address.strip() or None,
        "timezone": timezone,
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return RedirectResponse(f"/portal/sites?success=Site+'{name}'+created+successfully!", status_code=303)


# ---------------------------------------------------------------------------
# Integrations / Webhooks  (self-serve)
# ---------------------------------------------------------------------------


@router.get("/integrations", response_class=HTMLResponse)
async def portal_integrations(request: Request, success: str = "", error: str = "") -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    from bip.api.routes.v1 import _webhook_secrets, _webhooks

    org_id = sess["org_id"]
    data = _org_context(sess)
    webhooks = [w for w in _webhooks.values() if w.get("org_id") == org_id]

    return _render(
        request,
        "portal_integrations.html",
        _ctx(
            request, sess, "integrations",
            org=data["org"],
            webhooks=webhooks,
            secrets=_webhook_secrets,
            success=success,
            error=error,
        ),
    )


@router.post("/integrations/webhooks")
async def portal_integrations_post(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    import secrets
    import uuid
    from datetime import UTC, datetime

    from bip.api.routes.v1 import _webhook_secrets, _webhooks

    wh_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    _webhooks[wh_id] = {
        "id": wh_id,
        "name": name.strip(),
        "org_id": sess["org_id"],
        "url": url.strip(),
        "events": ["punch.created", "device.status_changed"],
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _webhook_secrets[wh_id] = secret

    return RedirectResponse(
        f"/portal/integrations?success=Webhook+'{name}'+connected!+Copy+your+signing+secret+below.",
        status_code=303,
    )


@router.post("/integrations/webhooks/{wh_id}/delete")
async def portal_webhook_delete(request: Request, wh_id: str) -> Any:
    sess = _require_session(request)
    if not sess:
        return RedirectResponse("/portal/login", status_code=303)

    from bip.api.routes.v1 import _webhook_secrets, _webhooks

    wh = _webhooks.get(wh_id)
    if wh and wh.get("org_id") == sess["org_id"]:
        del _webhooks[wh_id]
        _webhook_secrets.pop(wh_id, None)

    return RedirectResponse("/portal/integrations?success=Webhook+removed.", status_code=303)
