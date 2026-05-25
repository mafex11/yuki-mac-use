"""Idle source — emits IDLE_START / IDLE_END based on system idle seconds."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from yuki.observer.events import Event, EventKind
from yuki.observer.ringbuffer import RingBuffer
from yuki.observer.sources.base import Source


async def _default_get_idle() -> float:  # pragma: no cover — real macOS only
    try:
        import Quartz  # type: ignore[import-untyped]

        seconds: float = Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateHIDSystemState,
            Quartz.kCGAnyInputEventType,
        )
        return seconds
    except Exception:
        return 0.0


class IdleSource(Source):
    name = "idle"

    def __init__(
        self,
        get_idle: Callable[[], Awaitable[float]] | None = None,
        threshold: float = 60.0,
    ) -> None:
        super().__init__()
        self._get_idle = get_idle or _default_get_idle
        self._threshold = threshold
        self._is_idle = False

    async def iterate(self, buffer: RingBuffer) -> None:
        seconds = await self._get_idle()
        if seconds >= self._threshold and not self._is_idle:
            self._is_idle = True
            await buffer.push(
                Event(
                    ts=datetime.now(UTC),
                    kind=EventKind.IDLE_START,
                    payload={"seconds": seconds},
                )
            )
        elif seconds < self._threshold and self._is_idle:
            self._is_idle = False
            await buffer.push(
                Event(ts=datetime.now(UTC), kind=EventKind.IDLE_END, payload={})
            )
