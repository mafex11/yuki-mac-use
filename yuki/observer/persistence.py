"""Persister — flushes ring buffer events to SQLite events table.

Reuses the same DB as the memory indexer (yuki/memory/paths.py); events live
in a separate table so they don't interfere with FTS5 / sqlite-vec writes.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta

from yuki.memory import paths
from yuki.observer.events import Event


class Persister:
    def __init__(self) -> None:
        self._db_path = paths.index_db_path()
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                ts INTEGER NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
            """
        )
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Persister not opened")
        return self._conn

    def flush(self, events: list[Event]) -> None:
        if not events:
            return
        rows = [e.to_row() for e in events]
        self.conn.executemany(
            "INSERT INTO events(ts, kind, payload) VALUES (?, ?, ?)", rows
        )
        self.conn.commit()

    def purge_old(self) -> int:
        days = int(os.environ.get("YUKI_EVENT_RETENTION_DAYS", "30"))
        cutoff_ms = int(
            (datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000
        )
        cur = self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff_ms,))
        self.conn.commit()
        return cur.rowcount

    def row_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0])
