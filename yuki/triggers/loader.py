"""Loader — reads/writes trigger markdown notes."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from yuki.memory import frontmatter, paths
from yuki.memory.schemas import TriggerNote, parse_note
from yuki.triggers.trigger import Trigger

log = logging.getLogger(__name__)


def _triggers_dir() -> Path:
    return paths.vault_dir() / "30-Routines" / "triggers"


def load_all() -> list[Trigger]:
    out: list[Trigger] = []
    d = _triggers_dir()
    if not d.exists():
        return out
    for path in d.glob("*.md"):
        try:
            meta, body = frontmatter.read_file(path)
            note = parse_note(meta)
        except Exception as e:
            log.warning("trigger %s skipped: %s", path.name, e)
            continue
        if not isinstance(note, TriggerNote):
            continue
        if not note.enabled:
            continue
        out.append(Trigger.from_note(note, source_path=path, body=body))
    return out


def save_state(trigger: Trigger) -> None:
    if trigger.source_path is None or not trigger.source_path.exists():
        return
    meta, body = frontmatter.read_file(trigger.source_path)
    meta["fire_count"] = trigger.fire_count
    meta["acceptance_rate"] = trigger.acceptance_rate
    if trigger.last_fired is not None:
        meta["last_fired"] = trigger.last_fired.isoformat()
    meta["updated_at"] = datetime.now(UTC).isoformat()
    frontmatter.write_file(trigger.source_path, meta, body)
