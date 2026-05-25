"""VaultDiff — the structured output of compaction; can apply itself.

LLM-produced note dicts often omit timestamp/confidence frontmatter; apply()
fills them in (now, now, entry.confidence) before validating against the schema.
High-confidence entries (>=0.85) write to their normal section; lower entries
land in 90-Inbox/ for human review.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ValidationError

from yuki.memory.schemas import parse_note
from yuki.memory.vault import Vault, VaultError

log = logging.getLogger(__name__)
_HIGH = 0.85


@dataclass
class DiffEntry:
    action: Literal["create", "update"]
    note: dict[str, Any]
    confidence: float


@dataclass
class VaultDiff:
    entries: list[DiffEntry] = field(default_factory=list)

    @classmethod
    def from_json(cls, text: str) -> VaultDiff:
        data = json.loads(text)
        return cls(
            entries=[
                DiffEntry(
                    action=e.get("action", "create"),
                    note=e["note"],
                    confidence=float(e["confidence"]),
                )
                for e in data.get("entries", [])
            ]
        )

    def apply(self, *, vault: Vault) -> int:
        applied = 0
        now_iso = datetime.now(UTC).isoformat()
        for entry in self.entries:
            data = dict(entry.note)
            data.setdefault("created_at", now_iso)
            data.setdefault("updated_at", now_iso)
            data.setdefault("confidence", entry.confidence)
            try:
                note = parse_note(data)
            except ValidationError as e:
                log.warning("invalid diff entry skipped: %s", e)
                continue
            try:
                vault.write(
                    note,
                    body="",
                    route_low_confidence=(entry.confidence < _HIGH),
                )
                applied += 1
            except VaultError as e:
                log.warning("apply failed: %s", e)
        return applied
