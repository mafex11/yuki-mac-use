"""Trigger — runtime object backed by a TriggerNote markdown file."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from yuki.memory.schemas import TriggerNote

_DEBOUNCE_RE = re.compile(r"^(\d+)\s*([smhd])$")
_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_debounce(s: str) -> int:
    m = _DEBOUNCE_RE.match(s.strip().lower()) if s else None
    if not m:
        return 60
    return int(m.group(1)) * _UNIT[m.group(2)]


@dataclass
class Trigger:
    id: str
    condition_kind: str
    condition: dict[str, Any]
    action: dict[str, Any]
    debounce_seconds: int
    last_fired: datetime | None
    fire_count: int
    acceptance_rate: float
    source_path: Path | None = None
    body: str = ""
    _accept_history: list[bool] = field(default_factory=list)

    @classmethod
    def from_note(cls, note: TriggerNote, source_path: Path, body: str) -> Trigger:
        cond = note.condition.model_dump()
        return cls(
            id=note.id,
            condition_kind=cond["kind"],
            condition=cond,
            action=note.action.model_dump(),
            debounce_seconds=_parse_debounce(note.debounce),
            last_fired=note.last_fired,
            fire_count=note.fire_count,
            acceptance_rate=note.acceptance_rate,
            source_path=source_path,
            body=body,
        )

    def record_fire(self, *, accepted: bool) -> None:
        self._accept_history.append(accepted)
        self.fire_count += 1
        self.acceptance_rate = sum(self._accept_history) / len(self._accept_history)
