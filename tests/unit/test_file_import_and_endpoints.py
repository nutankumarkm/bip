"""Tests for FileImporter, FileImportConnector, and consumer vendor/import endpoints (M7)."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from bip.api.app import app
from bip.api.auth import clear_orgs, create_access_token, register_org
from bip.api.routes.v1 import _punches, reset_stores
from bip.connectors.file_import.adapter import FileImportConnector
from bip.connectors.file_import.importer import FileImporter
from bip.sdk.conformance import run_conformance
from bip.sdk.events import DeviceTarget

client = TestClient(app)

PARTNER_ID = "00000000-0000-0000-0000-000000000001"
ORG_ID = "00000000-0000-0000-0000-000000000002"
SITE_ID = "00000000-0000-0000-0000-000000000003"


def _auth_headers(scopes: list[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        {
            "client_id": "test-client-1",
            "partner_id": PARTNER_ID,
            "scopes": scopes or ["devices:write", "devices:read", "imports:write"],
        }
    )
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    reset_stores()
    clear_orgs()
    register_org(ORG_ID, PARTNER_ID)


def test_file_importer_csv_validation_report() -> None:
    """CSV parser produces row-level validation report flagging bad rows."""
    csv_content = """pin,timestamp,verify_mode
1001,2026-10-21 08:30:00,fingerprint
1002,not-a-valid-timestamp,card
,2026-10-21 08:32:00,fingerprint
1004,2026-10-21 08:35:00,face
"""
    importer = FileImporter()
    report = importer.parse_csv(csv_content)

    assert report.rows_total == 4
    assert report.rows_ok == 2
    assert report.rows_failed == 2
    assert len(report.errors) == 2

    # Check error details
    err_rows = [e.row for e in report.errors]
    assert 3 in err_rows  # Row 3 (line 3): invalid timestamp
    assert 4 in err_rows  # Row 4 (line 4): empty PIN

    assert len(report.punches) == 2
    assert report.punches[0].device_pin == "1001"
    assert report.punches[1].device_pin == "1004"


def test_file_importer_xlsx_validation_report() -> None:
    """XLSX parser validates rows and reports failures."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["User ID", "Date Time", "Status"])
    ws.append(["5001", "2026-10-21 09:00:00", "1"])
    ws.append(["5002", "INVALID_DATE", "1"])
    ws.append(["5003", "2026-10-21 09:15:00", "3"])

    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    importer = FileImporter()
    report = importer.parse_xlsx(content)

    assert report.rows_total == 3
    assert report.rows_ok == 2
    assert report.rows_failed == 1
    assert report.errors[0].row == 3


def test_file_importer_dat_format() -> None:
    """ZK USB attlog.dat parsing with validation."""
    dat_content = """
101   2026-10-21 08:00:00   1   1
102   2026-10-21 08:05:00   1   2
BAD_ROW_TOO_SHORT
104   2026-10-21 08:15:00   1   4
"""
    importer = FileImporter()
    report = importer.parse_dat(dat_content)

    assert report.rows_total == 4
    assert report.rows_ok == 3
    assert report.rows_failed == 1
    assert report.errors[0].row == 3


@pytest.mark.asyncio
async def test_file_import_connector_conformance(tmp_path: Path) -> None:
    """Run SDK conformance harness against FileImportConnector."""
    csv_file = tmp_path / "attendance.csv"
    lines = ["pin,timestamp,verify_mode\n"]
    for i in range(25):
        lines.append(f"USER{i},2026-10-21 08:{i:02d}:00,fingerprint\n")
    csv_file.write_text("".join(lines))

    conn = FileImportConnector(file_path=csv_file, format="csv")
    target = DeviceTarget(address="local_file", serial="FILE-01")

    result = await run_conformance(
        conn,
        target,
        capabilities=conn.CAPABILITIES,
        punch_count=25,
    )
    assert result.ok, f"FileImport conformance failed: {result.failed}, errors: {result.errors}"


def test_vendor_connections_consumer_api() -> None:
    """Consumer API can register and list vendor connections (BioTime / COSEC)."""
    headers = _auth_headers(["devices:write", "devices:read"])

    # 1. Register BioTime connection
    resp = client.post(
        f"/v1/orgs/{ORG_ID}/vendor-connections",
        json={
            "site_id": SITE_ID,
            "vendor": "biotime",
            "base_url": "https://biotime.school.edu",
            "credentials": {"token": "secret-biotime-token"},
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    conn_id = data["id"]
    assert data["vendor"] == "biotime"
    assert data["status"] == "active"
    # Credentials must NOT be returned in plaintext response
    assert "token" not in data
    assert "credentials" not in data

    # 2. List connections
    list_resp = client.get(f"/v1/orgs/{ORG_ID}/vendor-connections", headers=headers)
    assert list_resp.status_code == 200
    assert any(c["id"] == conn_id for c in list_resp.json())


def test_file_import_consumer_api_with_validation_report() -> None:
    """Consumer API upload file import, returns validation report, and ingests punches."""
    headers = _auth_headers(["imports:write", "devices:read"])

    csv_data = """pin,timestamp,verify_mode
9001,2026-10-21 07:45:00,fingerprint
9002,bad-timestamp,card
9003,2026-10-21 07:50:00,face
"""

    resp = client.post(
        f"/v1/orgs/{ORG_ID}/imports",
        json={
            "site_id": SITE_ID,
            "filename": "morning_shift.csv",
            "format": "csv",
            "content_text": csv_data,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    report = resp.json()
    import_id = report["id"]

    assert report["rows_total"] == 3
    assert report["rows_ok"] == 2
    assert report["rows_failed"] == 1
    assert len(report["errors"]) == 1

    # Check that 2 punches were ingested into the system
    assert len(_punches) == 2
    assert _punches[0]["device_pin"] == "9001"
    assert _punches[1]["device_pin"] == "9003"

    # Get import report via GET
    get_resp = client.get(f"/v1/orgs/{ORG_ID}/imports/{import_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == import_id
