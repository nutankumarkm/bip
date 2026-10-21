"""Gateway API routes — cloud-side endpoints for gateway agent communication and consumer management.

Implements ADR-009, section 10 and section 11.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from bip.api.auth import TokenPayload, check_org_access, require_scope
from bip.gateway.keys import (
    generate_keypair,
    public_key_from_b64,
    public_key_from_hex,
    public_key_to_b64,
    verify_request,
)
from bip.gateway.updater import build_manifest_canonical_bytes

# Consumer API router (prefixed /v1)
consumer_gateway_router = APIRouter(prefix="/v1")

# Gateway Agent API router (prefixed /gw/v1)
gateway_api_router = APIRouter(prefix="/gw/v1")


# --- Master update key for release manifest signing ---
_release_priv_key, _release_pub_key = generate_keypair()


def get_release_public_key_b64() -> str:
    return public_key_to_b64(_release_pub_key)


# --- Request/response models ---


class GatewayRegister(BaseModel):
    site_id: str
    name: str


class GatewayPairRequest(BaseModel):
    code: str
    public_key: str
    hostname: str | None = None
    version: str | None = None


class GatewayHeartbeat(BaseModel):
    version: str = "0.1.0"
    queue_depth: int = 0
    disk_free_mb: float = 0
    devices: list[dict[str, Any]] = Field(default_factory=list)


class BatchPunchesRequest(BaseModel):
    batch_id: str
    device_id: str
    events: list[dict[str, Any]] = Field(default_factory=list)


class GatewayCommandResult(BaseModel):
    command_id: str
    success: bool
    return_code: int = 0
    message: str = ""
    result: dict[str, Any] | None = None


class DiscoveredDevicesRequest(BaseModel):
    devices: list[dict[str, Any]] = Field(default_factory=list)


class DeviceAssign(BaseModel):
    device_id: str


# --- In-memory stores for testing ---

_gateways: dict[str, dict[str, Any]] = {}
_pairing_codes: dict[str, dict[str, Any]] = {}
_processed_batches: dict[str, dict[str, Any]] = {}
_discovered_devices: list[dict[str, Any]] = []


def reset_gateway_stores() -> None:
    _gateways.clear()
    _pairing_codes.clear()
    _processed_batches.clear()
    _discovered_devices.clear()


# =============================================================================
# Gateway Authentication Dependency (ADR-009)
# =============================================================================


async def verify_gateway_auth(
    request: Request,
    x_bip_gateway: str = Header(..., alias="X-BIP-Gateway"),
    x_bip_timestamp: str = Header(..., alias="X-BIP-Timestamp"),
    x_bip_signature: str = Header(..., alias="X-BIP-Signature"),
) -> dict[str, Any]:
    """Verify Ed25519 request signature and timestamp skew (under 300 s)."""
    # 1. Verify timestamp skew
    try:
        ts = int(x_bip_timestamp)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp header") from None

    now_ts = int(time.time())
    if abs(now_ts - ts) > 300:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request timestamp skew exceeds 300 seconds",
        )

    # 2. Lookup gateway
    gw = _gateways.get(x_bip_gateway)
    if not gw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Gateway not found")
    if gw.get("status") != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gateway is not active")

    pub_key_str = gw.get("public_key")
    if not pub_key_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Gateway public key not registered")

    # 3. Load public key
    try:
        public_key = public_key_from_hex(pub_key_str) if len(pub_key_str) == 64 else public_key_from_b64(pub_key_str)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid stored public key") from None

    # 4. Verify signature over <METHOD>\n<path with query>\n<timestamp>\n<sha256 hex of body>
    body = await request.body()
    path_with_query = request.url.path
    if request.url.query:
        path_with_query += f"?{request.url.query}"

    if not verify_request(public_key, x_bip_signature, request.method, path_with_query, body, ts):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid request signature")

    return gw


# =============================================================================
# Consumer API: /v1/orgs/{org_id}/gateways
# =============================================================================


@consumer_gateway_router.post("/orgs/{org_id}/gateways", status_code=status.HTTP_201_CREATED)
async def register_gateway(
    org_id: str,
    body: GatewayRegister,
    client: TokenPayload = Depends(require_scope("gateways:write")),
) -> dict[str, Any]:
    check_org_access(org_id, client)
    gw_id = str(uuid.uuid4())
    # 8-digit numeric pairing code valid for 15 minutes per spec
    pairing_code = f"{secrets.randbelow(100000000):08d}"
    code_hash = hashlib.sha256(pairing_code.encode()).hexdigest()

    gateway = {
        "id": gw_id,
        "org_id": org_id,
        "site_id": body.site_id,
        "name": body.name,
        "status": "pairing",
        "public_key": None,
        "version": None,
        "last_seen_at": None,
        "queue_depth": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _gateways[gw_id] = gateway

    pc_id = str(uuid.uuid4())
    _pairing_codes[pc_id] = {
        "id": pc_id,
        "gateway_id": gw_id,
        "code_hash": code_hash,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        "used_at": None,
    }

    return {**gateway, "pairing_code": pairing_code}


@consumer_gateway_router.get("/orgs/{org_id}/gateways")
async def list_gateways(
    org_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> list[dict[str, Any]]:
    check_org_access(org_id, client)
    return [gw for gw in _gateways.values() if gw["org_id"] == org_id]


@consumer_gateway_router.get("/orgs/{org_id}/gateways/{gateway_id}")
async def get_gateway(
    org_id: str,
    gateway_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> dict[str, Any]:
    check_org_access(org_id, client)
    gw = _gateways.get(gateway_id)
    if not gw or gw["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Gateway not found")
    return gw


@consumer_gateway_router.delete("/orgs/{org_id}/gateways/{gateway_id}", status_code=status.HTTP_200_OK)
async def revoke_gateway(
    org_id: str,
    gateway_id: str,
    client: TokenPayload = Depends(require_scope("gateways:write")),
) -> dict[str, Any]:
    check_org_access(org_id, client)
    gw = _gateways.get(gateway_id)
    if not gw or gw["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Gateway not found")
    gw["status"] = "revoked"
    return {"status": "revoked", "id": gateway_id}


@consumer_gateway_router.post("/orgs/{org_id}/gateways/{gateway_id}/devices")
async def assign_device(
    org_id: str,
    gateway_id: str,
    body: DeviceAssign,
    client: TokenPayload = Depends(require_scope("devices:write")),
) -> dict[str, Any]:
    check_org_access(org_id, client)
    gw = _gateways.get(gateway_id)
    if not gw or gw["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Gateway not found")

    from bip.api.routes.v1 import _devices

    device = _devices.get(body.device_id)
    if not device or device["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Device not found")

    device["gateway_id"] = gateway_id
    device["mode"] = "gateway"
    return device


@consumer_gateway_router.get("/orgs/{org_id}/gateways/{gateway_id}/devices")
async def list_assigned_devices(
    org_id: str,
    gateway_id: str,
    client: TokenPayload = Depends(require_scope("devices:read")),
) -> list[dict[str, Any]]:
    check_org_access(org_id, client)
    gw = _gateways.get(gateway_id)
    if not gw or gw["org_id"] != org_id:
        raise HTTPException(status_code=404, detail="Gateway not found")

    from bip.api.routes.v1 import _devices

    return [d for d in _devices.values() if d.get("gateway_id") == gateway_id]


# =============================================================================
# Gateway API: /gw/v1/*
# =============================================================================


@gateway_api_router.post("/pair")
async def pair_gateway(body: GatewayPairRequest) -> dict[str, Any]:
    """Pair gateway agent using 8-digit pairing code and register public key."""
    code_hash = hashlib.sha256(body.code.encode()).hexdigest()
    valid_pc = None

    for pc in _pairing_codes.values():
        if (
            pc["code_hash"] == code_hash
            and pc["used_at"] is None
            and datetime.fromisoformat(pc["expires_at"]) > datetime.now(UTC)
        ):
            valid_pc = pc
            break

    if not valid_pc:
        raise HTTPException(status_code=401, detail="Invalid or expired pairing code")

    gw_id = valid_pc["gateway_id"]
    gw = _gateways.get(gw_id)
    if not gw:
        raise HTTPException(status_code=404, detail="Gateway not found")

    valid_pc["used_at"] = datetime.now(UTC).isoformat()
    gw["status"] = "active"
    gw["public_key"] = body.public_key
    if body.version:
        gw["version"] = body.version
    if body.hostname:
        gw["hostname"] = body.hostname

    config = {
        "poll_interval_seconds": 30,
        "heartbeat_interval_seconds": 60,
        "upload_batch_size": 100,
        "site_id": gw["site_id"],
        "org_id": gw["org_id"],
    }

    return {"gateway_id": gw_id, "config": config}


@gateway_api_router.get("/config")
async def get_config(
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    from bip.api.routes.v1 import _devices

    assigned = [
        {"id": d["id"], "serial": d.get("serial"), "family": d.get("family"), "address": d.get("address")}
        for d in _devices.values()
        if d.get("gateway_id") == gw["id"]
    ]
    return {
        "gateway_id": gw["id"],
        "org_id": gw["org_id"],
        "site_id": gw["site_id"],
        "poll_interval_seconds": 30,
        "heartbeat_interval_seconds": 60,
        "devices": assigned,
    }


@gateway_api_router.get("/commands")
async def long_poll_commands(
    wait: int = Query(default=30, ge=0, le=30),
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    """Long-poll for queued commands destined for this gateway's devices."""
    from bip.api.routes.v1 import _commands, _devices

    assigned_device_ids = {d["id"] for d in _devices.values() if d.get("gateway_id") == gw["id"]}

    def find_pending() -> list[dict[str, Any]]:
        return [
            cmd
            for cmd in _commands.values()
            if cmd["state"] == "queued"
            and (cmd["device_id"] in assigned_device_ids or cmd.get("org_id") == gw["org_id"])
        ]

    pending = find_pending()
    if not pending and wait > 0:
        # Wait up to `wait` seconds checking every 0.5s
        elapsed = 0.0
        while elapsed < float(wait):
            await asyncio.sleep(0.5)
            elapsed += 0.5
            pending = find_pending()
            if pending:
                break

    # Mark returned commands as sent
    now_iso = datetime.now(UTC).isoformat()
    for cmd in pending:
        cmd["state"] = "sent"
        cmd["sent_at"] = now_iso

    return {"commands": pending}


@gateway_api_router.post("/punches:batch")
async def upload_batch(
    body: BatchPunchesRequest,
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    """Upload a batch of punches. Idempotent on batch_id."""
    # Check idempotency
    if body.batch_id in _processed_batches:
        return _processed_batches[body.batch_id]

    from bip.api.routes.v1 import add_test_punch

    accepted = 0
    for p in body.events:
        ts = datetime.now(UTC)
        if "device_local_time" in p:
            with contextlib.suppress(ValueError):
                ts = datetime.fromisoformat(p["device_local_time"])
        elif "occurred_at" in p:
            with contextlib.suppress(ValueError):
                ts = datetime.fromisoformat(p["occurred_at"])

        add_test_punch(
            org_id=gw["org_id"],
            site_id=gw["site_id"],
            device_id=body.device_id,
            pin=str(p.get("device_pin", "")),
            occurred_at=ts,
            verify_mode=p.get("verify_mode", "fingerprint"),
            source="zk_tcp",
        )
        accepted += 1

    resp = {"accepted": accepted, "batch_id": body.batch_id}
    _processed_batches[body.batch_id] = resp
    return resp


@gateway_api_router.post("/commands/{cmd_id}/result")
async def post_command_result(
    cmd_id: str,
    body: GatewayCommandResult,
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    """Record result of an executed command."""
    from bip.api.routes.v1 import _commands

    cmd = _commands.get(cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd["state"] = "succeeded" if body.success else "failed"
    cmd["completed_at"] = datetime.now(UTC).isoformat()
    cmd["result"] = {"return_code": body.return_code, "message": body.message, "data": body.result}

    return {"status": "ok"}


@gateway_api_router.post("/heartbeat")
async def gateway_heartbeat(
    body: GatewayHeartbeat,
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    """Record gateway heartbeat and device status."""
    gw["last_seen_at"] = datetime.now(UTC).isoformat()
    gw["queue_depth"] = body.queue_depth
    gw["version"] = body.version
    gw["disk_free_mb"] = body.disk_free_mb

    from bip.api.routes.v1 import _devices

    for d_status in body.devices:
        dev_id = d_status.get("device_id")
        dev = _devices.get(dev_id)
        if dev:
            dev["last_seen_at"] = datetime.now(UTC).isoformat()
            dev["clock_drift_s"] = d_status.get("drift_s", 0)
            dev["log_fill_pct"] = d_status.get("log_fill_pct", 0)
            if d_status.get("reachable"):
                dev["status"] = "active"

    return {"status": "ok"}


@gateway_api_router.post("/discovered")
async def record_discovered(
    body: DiscoveredDevicesRequest,
    gw: dict[str, Any] = Depends(verify_gateway_auth),
) -> dict[str, Any]:
    """Record devices discovered on gateway LAN scan."""
    for dev in body.devices:
        _discovered_devices.append(
            {
                "gateway_id": gw["id"],
                "org_id": gw["org_id"],
                "discovered_at": datetime.now(UTC).isoformat(),
                **dev,
            }
        )
    return {"status": "ok", "recorded": len(body.devices)}


@gateway_api_router.get("/release")
async def get_release_manifest() -> dict[str, Any]:
    """Return signed agent update release manifest."""
    version = "0.2.0"
    url = "https://updates.bip.local/agent/bip-gateway-0.2.0.tar.gz"
    sha256_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    message = build_manifest_canonical_bytes(version, url, sha256_hash)
    sig = _release_priv_key.sign(message)
    sig_b64 = secrets.base64.b64encode(sig).decode("ascii")

    return {
        "version": version,
        "url": url,
        "sha256": sha256_hash,
        "signature": sig_b64,
    }
