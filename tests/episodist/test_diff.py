"""VaultDiff: high-confidence writes to section, low routes to inbox, invalid skipped."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yuki.episodist.diff import DiffEntry, VaultDiff
from yuki.memory.vault import Vault


def _entry(id_: str, confidence: float, **kw: Any) -> DiffEntry:
    base: dict[str, Any] = {
        "id": id_,
        "type": "routine",
        "name": "Morning",
        "schedule": "weekdays 8am",
        "steps": [],
        "trusted": False,
    }
    base.update(kw)
    return DiffEntry(action="create", note=base, confidence=confidence)


def test_high_confidence_writes_to_section(tmp_vault: Path) -> None:
    diff = VaultDiff(entries=[_entry("routine-morning", 0.9)])
    v = Vault()
    diff.apply(vault=v)
    note, _ = v.read("routine-morning")
    assert note.id == "routine-morning"


def test_low_confidence_routes_to_inbox(tmp_vault: Path) -> None:
    diff = VaultDiff(entries=[_entry("routine-x", 0.5)])
    v = Vault()
    diff.apply(vault=v)
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    assert len(inbox) == 1


def test_invalid_entry_skipped(tmp_vault: Path) -> None:
    diff = VaultDiff(
        entries=[DiffEntry(action="create", note={"type": "routine"}, confidence=0.9)]
    )
    v = Vault()
    applied = diff.apply(vault=v)
    assert applied == 0


def test_from_json_round_trip() -> None:
    payload = (
        '{"entries": [{"action": "create", "confidence": 0.9, '
        '"note": {"id": "routine-x", "type": "routine", "name": "X", '
        '"schedule": "?", "steps": [], "trusted": false}}]}'
    )
    diff = VaultDiff.from_json(payload)
    assert len(diff.entries) == 1
    assert diff.entries[0].confidence == 0.9
