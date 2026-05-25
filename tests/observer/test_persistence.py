"""Persister: table creation, flush, retention sweep."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.persistence import Persister


def _e(ts: datetime) -> Event:
    return Event(ts=ts, kind=EventKind.APP_FOCUS, payload={"x": 1})


def test_init_creates_table(tmp_index_db: Path) -> None:
    p = Persister()
    p.open()
    assert p.row_count() == 0
    p.close()


def test_flush_inserts_events(tmp_index_db: Path) -> None:
    p = Persister()
    p.open()
    now = datetime.now(UTC)
    p.flush([_e(now), _e(now + timedelta(seconds=1))])
    assert p.row_count() == 2
    p.close()


def test_flush_empty_is_noop(tmp_index_db: Path) -> None:
    p = Persister()
    p.open()
    p.flush([])
    assert p.row_count() == 0
    p.close()


def test_retention_deletes_old(tmp_index_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YUKI_EVENT_RETENTION_DAYS", "1")
    p = Persister()
    p.open()
    now = datetime.now(UTC)
    old = now - timedelta(days=5)
    p.flush([_e(old), _e(now)])
    p.purge_old()
    assert p.row_count() == 1
    p.close()
