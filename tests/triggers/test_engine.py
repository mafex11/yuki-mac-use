"""Engine: fires on matching event, respects debounce, ignores disabled."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from yuki.memory import frontmatter as fm
from yuki.observer.events import Event, EventKind
from yuki.triggers.engine import Engine
from yuki.triggers.presenter import InMemoryPresenter, Presenter


def _seed_calendar_trigger(vault: Path) -> Path:
    now = datetime(2026, 5, 22, tzinfo=UTC).isoformat()
    meta = {
        "id": "trigger-standup",
        "type": "trigger",
        "created_at": now,
        "updated_at": now,
        "confidence": 0.9,
        "source": ["user"],
        "enabled": True,
        "condition": {"kind": "calendar", "title_contains": "standup"},
        "debounce": "5m",
        "action": {"kind": "suggestion", "text": "Standup in 5"},
        "fire_count": 0,
        "acceptance_rate": 0.0,
    }
    path = vault / "30-Routines" / "triggers" / "standup.md"
    fm.write_file(path, meta, "")
    return path


async def test_engine_fires_on_matching_event(tmp_trigger_env: Path) -> None:
    _seed_calendar_trigger(tmp_trigger_env)
    presenter = InMemoryPresenter()
    presenters: dict[str, Presenter] = {
        "low": presenter,
        "medium": presenter,
        "high": presenter,
    }
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def feed() -> list[Event]:
        return [await queue.get()]

    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()

    await queue.put(
        Event(
            ts=datetime.now(UTC),
            kind=EventKind.EVENT_STARTING,
            payload={"id": "e1", "title": "Daily Standup", "start": "x"},
        )
    )
    await asyncio.sleep(0.2)
    await engine.stop()
    assert len(presenter.shown) == 1
    assert presenter.shown[0].trigger_id == "trigger-standup"


async def test_engine_respects_debounce(tmp_trigger_env: Path) -> None:
    _seed_calendar_trigger(tmp_trigger_env)
    presenter = InMemoryPresenter()
    presenters: dict[str, Presenter] = {
        "low": presenter,
        "medium": presenter,
        "high": presenter,
    }
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def feed() -> list[Event]:
        return [await queue.get()]

    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()
    for _ in range(3):
        await queue.put(
            Event(
                ts=datetime.now(UTC),
                kind=EventKind.EVENT_STARTING,
                payload={"id": "e", "title": "Standup", "start": "x"},
            )
        )
    await asyncio.sleep(0.3)
    await engine.stop()
    assert len(presenter.shown) == 1


async def test_engine_disabled_trigger_never_fires(tmp_trigger_env: Path) -> None:
    path = _seed_calendar_trigger(tmp_trigger_env)
    meta, body = fm.read_file(path)
    meta["enabled"] = False
    fm.write_file(path, meta, body)
    presenter = InMemoryPresenter()
    presenters: dict[str, Presenter] = {
        "low": presenter,
        "medium": presenter,
        "high": presenter,
    }
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def feed() -> list[Event]:
        return [await queue.get()]

    engine = Engine(presenters=presenters, drain_events=feed)
    await engine.start()
    await queue.put(
        Event(
            ts=datetime.now(UTC),
            kind=EventKind.EVENT_STARTING,
            payload={"id": "e1", "title": "Standup", "start": "x"},
        )
    )
    await asyncio.sleep(0.2)
    await engine.stop()
    assert presenter.shown == []
