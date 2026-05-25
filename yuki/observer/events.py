"""Event types emitted by observer sources."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    APP_FOCUS = "app_focus"
    WINDOW_FOCUS = "window_focus"
    WINDOW_TITLE = "window_title"
    URL_CHANGE = "url_change"
    IDLE_START = "idle_start"
    IDLE_END = "idle_end"
    EVENT_STARTING = "event_starting"
    EVENT_ENDED = "event_ended"
    FILE_MODIFIED = "file_modified"
    LOCK = "lock"
    UNLOCK = "unlock"
    SLEEP = "sleep"
    WAKE = "wake"
    POWER_SOURCE_CHANGED = "power_source_changed"
    WIFI_CHANGED = "wifi_changed"


@dataclass
class Event:
    ts: datetime
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "kind": self.kind.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            ts=datetime.fromisoformat(d["ts"]),
            kind=EventKind(d["kind"]),
            payload=dict(d.get("payload", {})),
        )

    def to_row(self) -> tuple[int, str, str]:
        ts_ms = int(self.ts.timestamp() * 1000)
        return ts_ms, self.kind.value, json.dumps(self.payload)
