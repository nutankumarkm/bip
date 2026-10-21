"""Unit tests for cryptographic audit chain and tamper detection (M9)."""

from __future__ import annotations

from datetime import UTC, datetime

from bip.api.ops.store import clear_ops_state, log_audit, verify_current_audit_log
from bip.core.audit import (
    GENESIS_HASH,
    AuditEntry,
    compute_audit_hash,
    verify_audit_chain,
)


def test_empty_audit_chain_is_valid() -> None:
    is_valid, err, seq = verify_audit_chain([])
    assert is_valid is True
    assert err is None
    assert seq is None


def test_valid_chain_verifies_successfully() -> None:
    entries: list[AuditEntry] = []
    prev = GENESIS_HASH

    for i in range(5):
        now = datetime.now(UTC)
        h = compute_audit_hash(
            seq=i,
            ts=now,
            actor="admin@example.com",
            action=f"action_{i}",
            resource_type="org",
            resource_id=f"org_{i}",
            detail={"step": i},
            prev_hash=prev,
        )
        entry = AuditEntry(
            seq=i,
            ts=now,
            actor="admin@example.com",
            action=f"action_{i}",
            resource_type="org",
            resource_id=f"org_{i}",
            detail={"step": i},
            prev_hash=prev,
            entry_hash=h,
        )
        entries.append(entry)
        prev = h

    is_valid, err, seq = verify_audit_chain(entries)
    assert is_valid is True
    assert err is None
    assert seq is None


def test_content_tampering_is_detected() -> None:
    clear_ops_state()
    log_audit("alice@test.com", "create_org", "org", "org_1", {"name": "Org 1"})
    e2 = log_audit("bob@test.com", "create_site", "site", "site_1", {"name": "Site 1"})
    log_audit("charlie@test.com", "revoke_gateway", "gateway", "gw_1")

    # Initial state is valid
    is_valid, _, _ = verify_current_audit_log()
    assert is_valid is True

    # Tamper with e2's action directly
    e2.action = "delete_all_databases"

    # Verifier must detect tampering at seq 1
    is_valid, err, seq = verify_current_audit_log()
    assert is_valid is False
    assert seq == 1
    assert "Tampered content" in str(err)


def test_link_tampering_is_detected() -> None:
    clear_ops_state()
    log_audit("alice@test.com", "create_org", "org", "org_1")
    e2 = log_audit("bob@test.com", "create_site", "site", "site_1")

    # Tamper with e2's prev_hash
    e2.prev_hash = "f" * 64

    is_valid, err, seq = verify_current_audit_log()
    assert is_valid is False
    assert seq == 1
    assert "Broken prev_hash" in str(err)


def test_middle_deletion_is_detected() -> None:
    clear_ops_state()
    e0 = log_audit("alice@test.com", "step_0", "org", "0")
    log_audit("bob@test.com", "step_1", "org", "1")
    e2 = log_audit("charlie@test.com", "step_2", "org", "2")

    # Chain with e1 omitted
    broken_chain = [e0, e2]
    is_valid, err, seq = verify_audit_chain(broken_chain)
    assert is_valid is False
    assert seq == 2
    assert "Broken prev_hash" in str(err)
