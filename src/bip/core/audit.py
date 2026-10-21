"""Cryptographic audit chain with SHA-256 hash chaining and tampering detection (M9)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

GENESIS_HASH = "0" * 64


class AuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    seq: int = 0
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str  # email or identifier of actor
    action: str  # e.g. "create_org", "revoke_gateway"
    resource_type: str
    resource_id: str
    detail: dict[str, Any] = Field(default_factory=dict)
    ip: str = ""
    prev_hash: str = GENESIS_HASH
    entry_hash: str = ""


def compute_audit_hash(
    seq: int,
    ts: datetime,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any],
    prev_hash: str,
) -> str:
    """Compute deterministic SHA-256 hash for an audit entry."""
    canonical_detail = json.dumps(detail, sort_keys=True, separators=(",", ":"))
    payload = f"{prev_hash}|{seq}|{ts.isoformat()}|{actor}|{action}|{resource_type}|{resource_id}|{canonical_detail}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_audit_chain(entries: list[AuditEntry]) -> tuple[bool, str | None, int | None]:
    """Verify cryptographic integrity of an audit chain.

    Returns:
        (is_valid, error_reason, broken_sequence_number)
    """
    if not entries:
        return True, None, None

    # Sort entries by sequence ascending for verification
    ordered = sorted(entries, key=lambda e: e.seq)

    for i, entry in enumerate(ordered):
        expected_prev = GENESIS_HASH if i == 0 else ordered[i - 1].entry_hash

        if entry.prev_hash != expected_prev:
            return (
                False,
                f"Broken prev_hash link at seq={entry.seq}: expected {expected_prev[:12]}..., got {entry.prev_hash[:12]}...",
                entry.seq,
            )

        expected_hash = compute_audit_hash(
            seq=entry.seq,
            ts=entry.ts,
            actor=entry.actor,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            detail=entry.detail,
            prev_hash=entry.prev_hash,
        )

        if entry.entry_hash != expected_hash:
            return (
                False,
                f"Tampered content at seq={entry.seq}: expected hash {expected_hash[:12]}..., got {entry.entry_hash[:12]}...",
                entry.seq,
            )

    return True, None, None
