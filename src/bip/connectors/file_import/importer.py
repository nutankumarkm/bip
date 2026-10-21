"""File import parser for CSV, XLSX, and ZK USB attlog.dat files (ADR-002, section 8.7)."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from bip.sdk.events import RawPunch, VerifyMode


class ImportErrorDetail(BaseModel):
    row: int
    error: str
    raw: dict[str, Any] | str | None = None


class ImportReport(BaseModel):
    status: str = "completed"
    rows_total: int = 0
    rows_ok: int = 0
    rows_failed: int = 0
    errors: list[ImportErrorDetail] = Field(default_factory=list)
    punches: list[RawPunch] = Field(default_factory=list)


def parse_timestamp(value: str) -> datetime:
    """Parse timestamp leniently supporting multiple ISO and common formats."""
    v = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    # Try fromisoformat as fallback
    return datetime.fromisoformat(v)


def parse_verify_mode(val: Any) -> VerifyMode:
    s = str(val).strip().lower()
    if s in ("1", "finger", "fingerprint", "fp"):
        return "fingerprint"
    if s in ("2", "pin", "password"):
        return "pin"
    if s in ("3", "card", "rfid", "badge"):
        return "card"
    if s in ("4", "face", "facial"):
        return "face"
    if s in ("5", "palm"):
        return "palm"
    return "other"


def find_column(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    # Normalize by lowercasing and replacing spaces with underscores for flexible matching
    headers_lower = {h.strip().lower(): h for h in headers}
    headers_norm = {h.strip().lower().replace(" ", "_"): h for h in headers}
    for c in candidates:
        if c in headers_lower:
            return headers_lower[c]
        if c in headers_norm:
            return headers_norm[c]
    return None


class FileImporter:
    """Parses attendance files into raw punches with row-level validation."""

    def parse_csv(
        self,
        content: str | bytes,
        mapping: dict[str, str] | None = None,
    ) -> ImportReport:
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        reader = csv.reader(io.StringIO(text))

        rows = list(reader)
        if not rows:
            return ImportReport(rows_total=0, rows_ok=0, rows_failed=0)

        header = rows[0]
        mapping = mapping or {}
        pin_col = mapping.get("pin") or find_column(header, ("pin", "user_id", "userid", "emp_code", "employee_id", "user id", "employee no"))
        time_col = mapping.get("timestamp") or find_column(header, ("timestamp", "time", "date", "datetime", "date_time", "date time", "punch_time", "log_date"))
        mode_col = mapping.get("verify_mode") or find_column(header, ("verify_mode", "verify", "mode", "status"))

        if not pin_col or not time_col:
            # Check if positional / headerless CSV
            pin_idx = 0
            time_idx = 1
            mode_idx = 2 if len(header) > 2 else None
            start_row = 0
        else:
            pin_idx = header.index(pin_col)
            time_idx = header.index(time_col)
            mode_idx = header.index(mode_col) if mode_col and mode_col in header else None
            start_row = 1

        report = ImportReport()
        report.rows_total = len(rows) - start_row

        for row_idx, row in enumerate(rows[start_row:], start=start_row + 1):
            if not row or all(not cell.strip() for cell in row):
                report.rows_total -= 1
                continue

            try:
                if len(row) <= max(pin_idx, time_idx):
                    raise ValueError(f"Missing required columns in row: {row}")

                pin = row[pin_idx].strip()
                if not pin:
                    raise ValueError("Empty PIN / User ID")

                ts_str = row[time_idx].strip()
                dt = parse_timestamp(ts_str)

                v_mode: VerifyMode = "other"
                if mode_idx is not None and len(row) > mode_idx:
                    v_mode = parse_verify_mode(row[mode_idx])

                punch = RawPunch(device_pin=pin, device_local_time=dt, verify_mode=v_mode)
                report.punches.append(punch)
                report.rows_ok += 1
            except Exception as e:
                report.rows_failed += 1
                report.errors.append(ImportErrorDetail(row=row_idx, error=str(e), raw=",".join(row)))

        return report

    def parse_xlsx(
        self,
        content: bytes,
        mapping: dict[str, str] | None = None,
    ) -> ImportReport:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        if not sheet:
            return ImportReport(rows_total=0, rows_ok=0, rows_failed=0)

        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return ImportReport(rows_total=0, rows_ok=0, rows_failed=0)

        header = [str(c or "").strip() for c in rows[0]]
        mapping = mapping or {}
        pin_col = mapping.get("pin") or find_column(header, ("pin", "user_id", "userid", "emp_code", "employee_id", "user id", "employee no"))
        time_col = mapping.get("timestamp") or find_column(header, ("timestamp", "time", "date", "datetime", "date_time", "date time", "punch_time", "log_date"))
        mode_col = mapping.get("verify_mode") or find_column(header, ("verify_mode", "verify", "mode", "status"))

        if not pin_col or not time_col:
            pin_idx = 0
            time_idx = 1
            mode_idx = 2 if len(header) > 2 else None
            start_row = 0
        else:
            pin_idx = header.index(pin_col)
            time_idx = header.index(time_col)
            mode_idx = header.index(mode_col) if mode_col and mode_col in header else None
            start_row = 1

        report = ImportReport()
        report.rows_total = len(rows) - start_row

        for row_idx, row in enumerate(rows[start_row:], start=start_row + 1):
            if not row or all(c is None for c in row):
                report.rows_total -= 1
                continue

            try:
                pin_val = row[pin_idx]
                if pin_val is None or str(pin_val).strip() == "":
                    raise ValueError("Empty PIN / User ID")
                pin = str(pin_val).strip()

                ts_val = row[time_idx]
                if isinstance(ts_val, datetime):
                    dt = ts_val
                else:
                    dt = parse_timestamp(str(ts_val))

                v_mode: VerifyMode = "other"
                if mode_idx is not None and len(row) > mode_idx and row[mode_idx] is not None:
                    v_mode = parse_verify_mode(row[mode_idx])

                punch = RawPunch(device_pin=pin, device_local_time=dt, verify_mode=v_mode)
                report.punches.append(punch)
                report.rows_ok += 1
            except Exception as e:
                report.rows_failed += 1
                report.errors.append(ImportErrorDetail(row=row_idx, error=str(e), raw=str(row)))

        return report

    def parse_dat(
        self,
        content: str | bytes,
    ) -> ImportReport:
        """Parse ZK USB attlog.dat format (whitespace/tab-separated)."""
        text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        report = ImportReport()
        report.rows_total = len(lines)

        for row_idx, line in enumerate(lines, start=1):
            parts = line.split()
            # Expected format: PIN Date Time Status VerifyMode WorkCode ...
            # e.g.: "1001 2026-10-21 08:30:00 1 1"
            if len(parts) < 3:
                report.rows_failed += 1
                report.errors.append(
                    ImportErrorDetail(row=row_idx, error="Line has fewer than 3 tokens", raw=line)
                )
                continue

            try:
                pin = parts[0]
                dt_str = f"{parts[1]} {parts[2]}"
                dt = parse_timestamp(dt_str)

                v_mode: VerifyMode = "fingerprint"
                if len(parts) >= 5:
                    v_mode = parse_verify_mode(parts[4])

                punch = RawPunch(device_pin=pin, device_local_time=dt, verify_mode=v_mode)
                report.punches.append(punch)
                report.rows_ok += 1
            except Exception as e:
                report.rows_failed += 1
                report.errors.append(ImportErrorDetail(row=row_idx, error=str(e), raw=line))

        return report
