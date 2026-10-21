"""Ops console in-memory data store — audit log, approvals, and read-through to API stores.

In production this would use SQLAlchemy + Postgres. For now it mirrors the same
in-memory approach used by the rest of the unit-testable layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from bip.core.audit import (
    GENESIS_HASH,
    AuditEntry,
    compute_audit_hash,
    verify_audit_chain,
)

ApprovalStatus = Literal["pending", "approved", "rejected"]


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action: str  # e.g. "revoke_gateway", "delete_org"
    resource_type: str
    resource_id: str
    detail: dict[str, Any] = Field(default_factory=dict)
    requested_by: str  # email
    reviewed_by: str | None = None
    status: ApprovalStatus = "pending"
    reviewed_at: datetime | None = None
    review_note: str = ""


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_AUDIT_LOG: list[AuditEntry] = []
_APPROVALS: dict[str, ApprovalRequest] = {}
_PARTNERS: dict[str, dict[str, Any]] = {
    "learnx": {
        "id": "learnx",
        "name": "LearnX Education",
        "created_at": datetime(2025, 1, 1, tzinfo=UTC),
    },
}


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def log_audit(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict[str, Any] | None = None,
    ip: str = "",
) -> AuditEntry:
    detail_dict = detail or {}
    seq = len(_AUDIT_LOG)
    prev_hash = _AUDIT_LOG[-1].entry_hash if _AUDIT_LOG else GENESIS_HASH
    now = datetime.now(UTC)
    entry_hash = compute_audit_hash(
        seq=seq,
        ts=now,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail_dict,
        prev_hash=prev_hash,
    )
    entry = AuditEntry(
        seq=seq,
        ts=now,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail_dict,
        ip=ip,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    _AUDIT_LOG.append(entry)
    return entry


def verify_current_audit_log() -> tuple[bool, str | None, int | None]:
    return verify_audit_chain(_AUDIT_LOG)


def list_audit(
    resource_type: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditEntry]:
    entries = list(reversed(_AUDIT_LOG))
    if resource_type:
        entries = [e for e in entries if e.resource_type == resource_type]
    if actor:
        entries = [e for e in entries if e.actor == actor]
    return entries[offset : offset + limit]


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------


def create_approval(
    action: str,
    resource_type: str,
    resource_id: str,
    requested_by: str,
    detail: dict[str, Any] | None = None,
) -> ApprovalRequest:
    req = ApprovalRequest(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        requested_by=requested_by,
        detail=detail or {},
    )
    _APPROVALS[req.id] = req
    return req


def get_approval(approval_id: str) -> ApprovalRequest | None:
    return _APPROVALS.get(approval_id)


def list_approvals(status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
    items = list(_APPROVALS.values())
    if status:
        items = [a for a in items if a.status == status]
    return sorted(items, key=lambda a: a.created_at, reverse=True)


def review_approval(
    approval_id: str,
    reviewed_by: str,
    approve: bool,
    note: str = "",
) -> ApprovalRequest | None:
    req = _APPROVALS.get(approval_id)
    if not req or req.status != "pending":
        return None
    req.status = "approved" if approve else "rejected"
    req.reviewed_by = reviewed_by
    req.reviewed_at = datetime.now(UTC)
    req.review_note = note
    return req


def clear_ops_state() -> None:
    """Test helper."""
    _AUDIT_LOG.clear()
    _APPROVALS.clear()
    _PARTNERS.clear()
    _PARTNERS.update(
        {
            "learnx": {
                "id": "learnx",
                "name": "LearnX Education",
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            },
        }
    )
