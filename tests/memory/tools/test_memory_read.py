"""memory_read tool — load + 1-hop wikilink expansion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault
from yuki.tools.memory.memory_read import memory_read


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=[],
        name=name,
    )


def test_read_by_id(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="manager")
    out = memory_read(id_or_path="person-sarah", vault=v)
    assert out["id"] == "person-sarah"
    assert "manager" in out["body"]  # type: ignore[operator]


def test_read_by_path(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="manager")
    md_file = next((tmp_vault / "10-People").glob("*.md"))
    out = memory_read(id_or_path=str(md_file), vault=v)
    assert out["id"] == "person-sarah"


def test_missing_raises(tmp_vault: Path) -> None:
    v = Vault()
    with pytest.raises(KeyError):
        memory_read(id_or_path="not-here", vault=v)


def test_expand_links_inlines_one_hop(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-sarah", "Sarah Chen"), body="great manager")
    v.write(
        _person("person-bob", "Bob Liu"),
        body="reports to [[person-sarah]] and likes ranking",
    )
    out = memory_read(id_or_path="person-bob", vault=v, expand_links=1)
    linked = out["linked"]
    assert isinstance(linked, list)
    assert any(n["id"] == "person-sarah" for n in linked)


def test_expand_links_zero(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-bob", "Bob Liu"), body="links to [[person-sarah]]")
    out = memory_read(id_or_path="person-bob", vault=v, expand_links=0)
    assert out.get("linked", []) == []
