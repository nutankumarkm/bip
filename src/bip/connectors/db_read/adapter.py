"""eTimeTrackLite read-only database connector adapter (ADR-002, section 8.6)."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

from bip.sdk.capabilities import Capability
from bip.sdk.errors import ProtocolError, Unreachable, Unsupported
from bip.sdk.events import (
    Checkpoint,
    CommandResult,
    DevicePerson,
    DeviceTarget,
    HealthReport,
    ProbeResult,
    RawPunch,
)


class DbReadConfig(BaseModel):
    connection_string: str = ""
    sqlite_path: str = ""  # For testing and file-based mock databases
    table_name: str = "DeviceLogs"
    column_user_id: str = "UserId"
    column_log_date: str = "LogDate"
    column_device_id: str = "DeviceId"


class ETimeTrackLiteConnector:
    """Read-only connector for eTimeTrackLite databases (SQL Server/Access via ODBC or SQLite for tests)."""

    family: str = "db_read"
    mode: Literal["pull"] = "pull"

    CAPABILITIES: ClassVar[set[Capability]] = {
        Capability.PUNCHES_PULL,
        Capability.DEVICE_INFO,
    }

    def __init__(self, config: DbReadConfig | None = None) -> None:
        self.config = config or DbReadConfig()

    def _get_connection(self) -> Any:
        # If sqlite_path is specified or connection_string starts with sqlite:, use sqlite3
        if self.config.sqlite_path:
            return sqlite3.connect(self.config.sqlite_path)
        if self.config.connection_string.startswith("sqlite:"):
            path = self.config.connection_string[7:]
            return sqlite3.connect(path)

        # Otherwise try pyodbc
        try:
            import pyodbc  # type: ignore[import-untyped]

            return pyodbc.connect(self.config.connection_string, readonly=True)
        except ImportError:
            raise Unreachable(
                "pyodbc is not installed. Install pyodbc extra for SQL Server/Access connections."
            ) from None
        except Exception as e:
            raise Unreachable(f"Failed to connect to database: {e}") from e

    async def probe(self, target: DeviceTarget) -> ProbeResult:
        """Verify database reachability and table presence."""

        def _do_probe() -> ProbeResult:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {self.config.table_name}")
                count = cur.fetchone()[0]
                conn.close()
                return ProbeResult(
                    serial=target.serial or "ETIMETRACKLITE-DB",
                    model="eTimeTrackLite DB",
                    capabilities=[c.value for c in self.CAPABILITIES],
                    extra={"row_count": count, "table": self.config.table_name},
                )
            except Exception as e:
                raise Unreachable(f"Failed to probe database: {e}") from e

        return await asyncio.to_thread(_do_probe)

    async def fetch_punches(self, since: Checkpoint) -> AsyncIterator[RawPunch]:
        """Fetch attendance punches newer than cursor."""

        def _fetch_rows() -> list[tuple[Any, Any, Any]]:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                sql = (
                    f"SELECT {self.config.column_user_id}, {self.config.column_log_date}, {self.config.column_device_id} "
                    f"FROM {self.config.table_name} "
                )
                params: list[Any] = []
                if since.cursor:
                    sql += f"WHERE {self.config.column_log_date} > ? "
                    params.append(since.cursor)
                sql += f"ORDER BY {self.config.column_log_date} ASC"

                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
                return rows
            except Exception as e:
                raise ProtocolError(f"Database query error: {e}") from e

        rows = await asyncio.to_thread(_fetch_rows)

        cursor_dt = None
        if since.cursor:
            with contextlib.suppress(ValueError):
                cursor_dt = datetime.fromisoformat(since.cursor)

        for row in rows:
            user_id, log_date, dev_id = row[0], row[1], row[2]
            if isinstance(log_date, str):
                try:
                    punch_dt = datetime.fromisoformat(log_date)
                except ValueError:
                    punch_dt = datetime.strptime(log_date, "%Y-%m-%d %H:%M:%S")
            else:
                punch_dt = log_date

            if cursor_dt and punch_dt <= cursor_dt:
                continue

            yield RawPunch(
                device_pin=str(user_id),
                device_local_time=punch_dt,
                verify_mode="fingerprint",
                raw={"user_id": user_id, "log_date": str(log_date), "device_id": str(dev_id)},
            )

    async def list_people(self) -> list[DevicePerson]:
        raise Unsupported("eTimeTrackLite connector is strictly read-only and does not support listing people")

    async def upsert_person(self, person: DevicePerson) -> CommandResult:
        raise Unsupported("eTimeTrackLite connector is strictly read-only; writing people is forbidden")

    async def delete_person(self, pin: str) -> CommandResult:
        raise Unsupported("eTimeTrackLite connector is strictly read-only; deleting people is forbidden")

    async def set_time(self, now: datetime) -> CommandResult:
        raise Unsupported("eTimeTrackLite connector is strictly read-only; cannot set device time")

    async def health(self) -> HealthReport:
        """Check database reachability."""

        def _do_health() -> HealthReport:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {self.config.table_name}")
                conn.close()
                return HealthReport(reachable=True, serial="ETIMETRACKLITE-DB")
            except Exception as e:
                return HealthReport(reachable=False, extra={"error": str(e)})

        return await asyncio.to_thread(_do_health)
