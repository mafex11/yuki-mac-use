"""Episodist test fixtures: temp index.db pre-seeded with events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.observer.events import Event, EventKind
from yuki.observer.persistence import Persister


@pytest.fixture
def seeded_events_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("YUKI_INDEX_DB", str(tmp_path / "index.db"))
    p = Persister()
    p.open()
    base = datetime(2026, 5, 21, 9, 0, tzinfo=UTC)
    events = [
        Event(
            ts=base,
            kind=EventKind.APP_FOCUS,
            payload={"bundle_id": "com.apple.Safari", "name": "Safari"},
        ),
        Event(
            ts=base.replace(minute=2),
            kind=EventKind.URL_CHANGE,
            payload={"url": "https://github.com/x", "browser": "Safari"},
        ),
        Event(
            ts=base.replace(hour=10),
            kind=EventKind.APP_FOCUS,
            payload={
                "bundle_id": "com.tinyspeck.slackmacgap",
                "name": "Slack",
            },
        ),
        Event(
            ts=base.replace(hour=12),
            kind=EventKind.IDLE_START,
            payload={"seconds": 60},
        ),
    ]
    p.flush(events)
    p.close()
    return tmp_path / "index.db"
