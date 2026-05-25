"""Reader: returns events for a date in chronological order."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from yuki.episodist.reader import read_events_for_date


def test_reads_events_for_date(seeded_events_db: Path) -> None:
    rows = read_events_for_date(date(2026, 5, 21))
    assert len(rows) == 4
    assert rows[0].kind.value == "app_focus"


def test_no_events_returns_empty(seeded_events_db: Path) -> None:
    rows = read_events_for_date(date(2026, 5, 1))
    assert rows == []


def test_rows_are_chronological(seeded_events_db: Path) -> None:
    rows = read_events_for_date(date(2026, 5, 21))
    times = [e.ts for e in rows]
    assert times == sorted(times)
