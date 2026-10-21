"""ADMS/iClock push protocol endpoints for the Device Edge."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from bip.connectors.zk_adms.parser import (
    parse_command_results,
    render_commands,
    render_handshake,
    strip_templates,
)
from bip.core.logging import get_logger
from bip.edge.store import EdgeStore

log = get_logger("bip.edge.adms")

router = APIRouter(prefix="/iclock")

_store = EdgeStore()


@router.get("/cdata")
async def handshake(
    request: Request,
    SN: str = Query(..., alias="SN"),
    options: str = Query("", alias="options"),
    pushver: str = Query("", alias="pushver"),
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    log.info("adms_handshake", serial=SN, ip=client_ip, options=options)

    device = await _store.lookup_device(SN)
    if device is None:
        await _store.upsert_pending(SN, client_ip, {"options": options, "pushver": pushver})
        stamp = await _store.get_checkpoint(SN, "attlog")
        body = render_handshake(SN, attlog_stamp=stamp or "None")
        return Response(content=body, media_type="text/plain")

    if device.get("status") == "disabled":
        return Response(content="ERR: Device disabled", status_code=403, media_type="text/plain")

    stamp = await _store.get_checkpoint(SN, "attlog")
    body = render_handshake(SN, attlog_stamp=stamp or "None")
    return Response(content=body, media_type="text/plain")


@router.post("/cdata")
async def upload(
    request: Request,
    SN: str = Query(..., alias="SN"),
    table: str = Query("", alias="table"),
    Stamp: str = Query("", alias="Stamp"),
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    body = (await request.body()).decode("utf-8", errors="replace")

    device = await _store.lookup_device(SN)
    if device is None:
        log.info("adms_upload_refused_unknown", serial=SN, table=table)
        await _store.upsert_pending(SN, client_ip, {"table": table})
        return Response(content="ERR: Unknown device", status_code=403, media_type="text/plain")

    cleaned_body = strip_templates(body)

    line_count = len([ln for ln in cleaned_body.strip().splitlines() if ln.strip()])

    await _store.save_raw_upload(
        device_id=device.get("id"),
        serial=SN,
        family="zk_adms",
        endpoint="cdata",
        query={"table": table, "Stamp": Stamp},
        body=cleaned_body,
    )

    # Ingest attendance punches into the central pipeline
    if table.upper() in ("ATTLOG", ""):
        try:
            from bip.api.routes.v1 import _devices, add_test_punch
            from bip.connectors.zk_adms.parser import parse_attlog

            parsed_punches = parse_attlog(cleaned_body)
            dev_info = next(
                (d for d in _devices.values() if d.get("serial") == SN or d.get("id") == device.get("id")),
                None,
            )
            org_id = dev_info.get("org_id", "org_default") if dev_info else device.get("org_id", "org_default")
            site_id = dev_info.get("site_id", "site_default") if dev_info else device.get("site_id", "site_default")
            dev_id = dev_info.get("id", device.get("id", SN)) if dev_info else device.get("id", SN)

            for p in parsed_punches:
                add_test_punch(
                    org_id=org_id,
                    site_id=site_id,
                    device_id=dev_id,
                    pin=p.device_pin,
                    occurred_at=p.device_local_time,
                    verify_mode=p.verify_mode,
                    source="adms",
                )
        except Exception as exc:
            log.warning("adms_ingest_error", serial=SN, error=str(exc))

    if Stamp:
        await _store.set_checkpoint(SN, "attlog", Stamp)

    log.info("adms_upload", serial=SN, table=table, lines=line_count)
    return Response(content=f"OK: {line_count}", media_type="text/plain")


@router.get("/getrequest")
async def getrequest(
    request: Request,
    SN: str = Query(..., alias="SN"),
) -> Response:
    device = await _store.lookup_device(SN)
    if device is None:
        await _store.upsert_pending(SN, request.client.host if request.client else "unknown", {})
        return Response(content="OK", media_type="text/plain")

    commands = await _store.get_pending_commands(device.get("id"))
    if not commands:
        return Response(content="OK", media_type="text/plain")

    rendered = render_commands(commands)
    for cmd_no, _ in commands:
        await _store.mark_command_sent(cmd_no)

    return Response(content=rendered, media_type="text/plain")


@router.post("/devicecmd")
async def devicecmd(
    request: Request,
    SN: str = Query(..., alias="SN"),
) -> Response:
    body = (await request.body()).decode("utf-8", errors="replace")
    results = parse_command_results(body)
    for result in results:
        if result.cmd_no is not None:
            await _store.complete_command(result.cmd_no, result.success, result.return_code)
    log.info("adms_cmd_results", serial=SN, count=len(results))
    return Response(content="OK", media_type="text/plain")


@router.get("/ping")
async def ping() -> Response:
    return Response(content="OK", media_type="text/plain")


@router.get("/registry")
async def registry() -> Response:
    return Response(content="OK", media_type="text/plain")


@router.get("/push")
async def push() -> Response:
    return Response(content="OK", media_type="text/plain")
