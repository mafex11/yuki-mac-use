"""Session segmentation — groups events into contiguous time blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from yuki.observer.events import Event


@dataclass
class Session:
    start: datetime
    end: datetime
    events: list[Event] = field(default_factory=list)

    def duration_minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


def segment(events: list[Event], gap_minutes: int = 5) -> list[Session]:
    if not events:
        return []
    gap = timedelta(minutes=gap_minutes)
    sessions: list[Session] = []
    current = Session(start=events[0].ts, end=events[0].ts, events=[events[0]])
    for ev in events[1:]:
        if ev.ts - current.end > gap:
            sessions.append(current)
            current = Session(start=ev.ts, end=ev.ts, events=[ev])
        else:
            current.end = ev.ts
            current.events.append(ev)
    sessions.append(current)
    return sessions
