"""Real-time webhook delivery and punch dispatch engine (ADR-004, ADR-008)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from bip.api.webhooks import sign_webhook

# In-memory delivery log for audit and Ops Console visualization
_delivery_log: list[dict[str, Any]] = []
_MAX_DELIVERY_LOGS = 100
_background_tasks: set[asyncio.Task[Any]] = set()


def get_delivery_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent webhook deliveries in reverse chronological order."""
    return list(reversed(_delivery_log[-limit:]))


def clear_delivery_logs() -> None:
    """Clear delivery logs (used in test teardown)."""
    _delivery_log.clear()


async def dispatch_webhook(
    webhook: dict[str, Any],
    secret: str,
    event_type: str,
    data: dict[str, Any],
    timeout_seconds: float = 4.0,
) -> dict[str, Any]:
    """Cryptographically sign and dispatch a JSON event to a consumer software webhook."""
    delivery_id = f"del_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(UTC).isoformat()
    payload = {
        "event": event_type,
        "event_id": f"evt_{uuid.uuid4().hex[:12]}",
        "timestamp": now_iso,
        "org_id": webhook.get("org_id", ""),
        "punch": data,
    }
    payload_str = json.dumps(payload, default=str)
    signature_header = sign_webhook(payload_str, secret)

    start_time = time.perf_counter()
    status_code = 0
    success = False
    error_msg: str | None = None

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                webhook["url"],
                content=payload_str,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BIP-Webhook-Delivery/1.0",
                    "BIP-Signature": signature_header,
                },
            )
            status_code = resp.status_code
            success = resp.is_success
            if not success:
                error_msg = f"HTTP {status_code}: {resp.text[:120]}"
    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

    log_entry = {
        "id": delivery_id,
        "timestamp": now_iso,
        "org_id": webhook.get("org_id", ""),
        "webhook_id": webhook.get("id", ""),
        "webhook_name": webhook.get("name", "Webhook"),
        "url": webhook.get("url", ""),
        "event": event_type,
        "punch_pin": data.get("device_pin", "—"),
        "device_id": data.get("device_id", "—"),
        "status_code": status_code,
        "success": success,
        "latency_ms": latency_ms,
        "error": error_msg,
    }

    _delivery_log.append(log_entry)
    if len(_delivery_log) > _MAX_DELIVERY_LOGS:
        _delivery_log.pop(0)

    return log_entry


def trigger_punch_dispatch(org_id: str, punch: dict[str, Any]) -> None:
    """Trigger non-blocking background dispatch of a new punch to all matching webhooks."""
    from bip.api.routes.v1 import _webhook_secrets, _webhooks

    target_webhooks = [
        (w, _webhook_secrets.get(w["id"], "default_secret"))
        for w in _webhooks.values()
        if (w.get("active", True) and (w.get("org_id") == org_id or w.get("org_id") == "all"))
    ]

    if not target_webhooks:
        return

    async def _dispatch_all() -> None:
        tasks = [
            dispatch_webhook(
                webhook=wh,
                secret=sec,
                event_type="punch.created",
                data=punch,
            )
            for wh, sec in target_webhooks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_dispatch_all())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # No running event loop (e.g. sync unit test or background thread without loop)
        with contextlib.suppress(Exception):
            asyncio.run(_dispatch_all())
