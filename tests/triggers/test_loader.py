"""Loader: reads enabled triggers, skips disabled / malformed; persists state."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.memory.frontmatter import write_file
from yuki.triggers.loader import load_all, save_state


def _write_trigger(
    vault: Path, slug: str, frontmatter: dict[str, Any], body: str = ""
) -> None:
    path = vault / "30-Routines" / "triggers" / f"{slug}.md"
    write_file(path, frontmatter, body)


def _base(slug: str = "standup") -> dict[str, Any]:
    now = datetime(2026, 5, 22, tzinfo=UTC).isoformat()
    return {
        "id": f"trigger-{slug}",
        "type": "trigger",
        "created_at": now,
        "updated_at": now,
        "confidence": 0.9,
        "source": ["user"],
        "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "standup time"},
        "fire_count": 0,
        "acceptance_rate": 0.0,
    }


def test_load_all_returns_enabled(tmp_trigger_env: Path) -> None:
    _write_trigger(tmp_trigger_env, "standup", _base("standup"))
    triggers = load_all()
    assert len(triggers) == 1
    assert triggers[0].id == "trigger-standup"


def test_load_skips_disabled(tmp_trigger_env: Path) -> None:
    _write_trigger(tmp_trigger_env, "x", _base("x") | {"enabled": False})
    assert load_all() == []


def test_save_state_persists_counters(tmp_trigger_env: Path) -> None:
    _write_trigger(tmp_trigger_env, "standup", _base("standup"))
    triggers = load_all()
    triggers[0].fire_count = 5
    triggers[0].acceptance_rate = 0.6
    save_state(triggers[0])
    again = load_all()
    assert again[0].fire_count == 5
    assert again[0].acceptance_rate == 0.6


def test_load_skips_malformed(tmp_trigger_env: Path) -> None:
    bad = tmp_trigger_env / "30-Routines" / "triggers" / "bad.md"
    bad.write_text("not yaml frontmatter")
    assert load_all() == []
