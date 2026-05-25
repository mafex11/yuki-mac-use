"""Reader — pulls observer events out of SQLite for a given date or date range."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, time, timedelta

from yuki.memory import paths
from yuki.observer.events import Event, EventKind


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(paths.index_db_path())


def read_events_between(start: datetime, end: datetime) -> list[Event]:
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT ts, kind, payload FROM events "
            "WHERE ts >= ? AND ts < ? ORDER BY ts ASC",
            (start_ms, end_ms),
        ).fetchall()
    finally:
        conn.close()
    out: list[Event] = []
    for ts_ms, kind, payload in rows:
        out.append(
            Event(
                ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                kind=EventKind(kind),
                payload=json.loads(payload) if payload else {},
            )
        )
    return out


def read_events_for_date(d: date) -> list[Event]:
    start = datetime.combine(d, time.min, tzinfo=UTC)
    return read_events_between(start, start + timedelta(days=1))
