"""SQLite-backed local outbox for durable punch queuing."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class LocalOutbox:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_serial TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                uploaded_at TEXT
            )"""
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_outbox_uploaded ON outbox(uploaded_at)")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS checkpoints (
                device_serial TEXT PRIMARY KEY,
                cursor TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def enqueue(self, device_serial: str, punches: list[dict[str, Any]]) -> int:
        if not punches:
            return 0
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(punches)
        cur = self._conn.execute(
            "INSERT INTO outbox (device_serial, payload, created_at) VALUES (?, ?, ?)",
            (device_serial, payload, now),
        )
        self._conn.commit()
        return cur.lastrowid or 0

    def peek(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, device_serial, payload, created_at FROM outbox WHERE uploaded_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"id": r[0], "device_serial": r[1], "punches": json.loads(r[2]), "created_at": r[3]} for r in rows]

    def mark_uploaded(self, ids: list[int]) -> None:
        if not ids:
            return
        now = datetime.now(UTC).isoformat()
        self._conn.executemany("UPDATE outbox SET uploaded_at = ? WHERE id = ?", [(now, i) for i in ids])
        self._conn.commit()

    def pending_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM outbox WHERE uploaded_at IS NULL").fetchone()
        return row[0] if row else 0

    def total_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM outbox").fetchone()
        return row[0] if row else 0

    def save_checkpoint(self, device_serial: str, cursor: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """INSERT INTO checkpoints (device_serial, cursor, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(device_serial) DO UPDATE SET cursor=excluded.cursor, updated_at=excluded.updated_at""",
            (device_serial, cursor, now),
        )
        self._conn.commit()

    def get_checkpoint(self, device_serial: str) -> str:
        row = self._conn.execute("SELECT cursor FROM checkpoints WHERE device_serial = ?", (device_serial,)).fetchone()
        return row[0] if row else ""

    def purge_uploaded(self, older_than_hours: int = 24) -> int:
        cutoff = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "DELETE FROM outbox WHERE uploaded_at IS NOT NULL AND uploaded_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cur.rowcount

    def get_punches_feed(self, after_id: int = 0, limit: int = 100) -> tuple[list[dict[str, Any]], int]:
        """Fetch individual punches for the local feed API ordered by outbox id."""
        rows = self._conn.execute(
            "SELECT id, device_serial, payload, created_at FROM outbox WHERE id > ? ORDER BY id ASC LIMIT ?",
            (after_id, limit),
        ).fetchall()

        all_punches: list[dict[str, Any]] = []
        last_id = after_id
        for r in rows:
            row_id = r[0]
            last_id = row_id
            serial = r[1]
            punches_list = json.loads(r[2])
            for p in punches_list:
                punch_item = dict(p)
                punch_item["_seq"] = row_id
                punch_item["device_serial"] = serial
                all_punches.append(punch_item)
                if len(all_punches) >= limit:
                    return all_punches, last_id

        return all_punches, last_id

    def close(self) -> None:
        self._conn.close()
