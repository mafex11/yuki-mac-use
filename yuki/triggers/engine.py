"""Engine — subscribes to events + ticker, matches triggers, fires presenters."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime

from yuki.observer.events import Event
from yuki.triggers.audit import append_to_audit
from yuki.triggers.conditions import matches_any
from yuki.triggers.debounce import DebounceGuard
from yuki.triggers.loader import load_all, save_state
from yuki.triggers.presenter import Presenter, Suggestion, pick_presenter
from yuki.triggers.pruner import maybe_propose_disable
from yuki.triggers.ticker import TimeTicker
from yuki.triggers.trigger import Trigger

log = logging.getLogger(__name__)


def _urgency_for(trigger: Trigger) -> str:
    return str(trigger.action.get("urgency", "medium"))


def _suggestion_text(trigger: Trigger) -> str:
    return str(trigger.action.get("text", trigger.id))


class Engine:
    def __init__(
        self,
        presenters: dict[str, Presenter],
        drain_events: Callable[[], Awaitable[list[Event]]],
        ticker_interval: float = 30.0,
    ) -> None:
        self._presenters = presenters
        self._drain = drain_events
        self._guard = DebounceGuard()
        self._triggers: list[Trigger] = []
        self._event_task: asyncio.Task[None] | None = None
        self._ticker = TimeTicker(self._on_tick, interval=ticker_interval)
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._triggers = load_all()
        self._event_task = asyncio.create_task(self._event_loop())
        await self._ticker.start()

    async def stop(self) -> None:
        self._stopping = True
        await self._ticker.stop()
        if self._event_task is not None:
            self._event_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._event_task
            self._event_task = None

    async def _event_loop(self) -> None:
        while not self._stopping:
            try:
                events = await self._drain()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("drain failed: %s", e)
                await asyncio.sleep(0.5)
                continue
            for ev in events:
                await self._handle_event(ev)

    async def _handle_event(self, event: Event) -> None:
        for trigger in self._triggers:
            if trigger.condition_kind == "time":
                continue
            if not matches_any(trigger, event):
                continue
            await self._fire(trigger, when=event.ts)

    async def _on_tick(self, now: datetime) -> None:
        for trigger in self._triggers:
            if trigger.condition_kind != "time":
                continue
            if not matches_any(trigger, now):
                continue
            await self._fire(trigger, when=now)

    async def _fire(self, trigger: Trigger, *, when: datetime) -> None:
        if not self._guard.allow(trigger, when):
            return
        suggestion = Suggestion(
            trigger_id=trigger.id,
            text=_suggestion_text(trigger),
            urgency=_urgency_for(trigger),
            ts=when,
        )
        try:
            presenter = pick_presenter(suggestion, self._presenters)
            await presenter.present(suggestion)
        except Exception as e:
            log.warning("presenter failed for %s: %s", trigger.id, e)
            return
        self._guard.mark_fired(trigger, when)
        # Acceptance is set later when user clicks Yes/No; for now record the fire.
        trigger.record_fire(accepted=False)
        append_to_audit(suggestion, accepted=False)
        save_state(trigger)
        maybe_propose_disable(trigger)
