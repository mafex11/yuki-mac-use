"""Vault — write/read/list/walk + wikilink resolution + low-confidence routing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yuki.memory.schemas import PersonNote
from yuki.memory.vault import Vault, VaultError


def _person(id_: str = "person-sarah-chen", name: str = "Sarah Chen") -> PersonNote:
    now = datetime(2026, 5, 22, 9, 0, tzinfo=UTC)
    return PersonNote(
        id=id_,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["calendar"],
        name=name,
    )


def test_write_then_read_round_trip(tmp_vault: Path) -> None:
    v = Vault()
    note = _person()
    v.write(note, body="Engineering manager.")
    fetched, body = v.read(note.id)
    assert fetched == note
    assert body.strip() == "Engineering manager."


def test_write_routes_by_type(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person(), body="x")
    files = list((tmp_vault / "10-People").glob("*.md"))
    assert len(files) == 1


def test_filename_is_slugified(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person(name="Sarah O'Chen"), body="x")
    files = list((tmp_vault / "10-People").glob("*.md"))
    # Apostrophe gets stripped during slugify
    assert files[0].name in {"Sarah-OChen.md", "Sarah-O-Chen.md"}


def test_id_resolves_after_filename_change(tmp_vault: Path) -> None:
    v = Vault()
    note = _person()
    v.write(note, body="x")
    src = next((tmp_vault / "10-People").glob("*.md"))
    src.rename(src.with_name("Renamed.md"))
    fetched, _ = v.read(note.id)
    assert fetched.id == note.id


def test_list_section(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-a", "A"), body="")
    v.write(_person("person-b", "B"), body="")
    items = v.list_section("10-People")
    assert {n.id for n, _ in items} == {"person-a", "person-b"}


def test_read_missing_raises(tmp_vault: Path) -> None:
    v = Vault()
    with pytest.raises(VaultError):
        v.read("nope-not-here")


def test_resolve_wikilink_by_id(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person(), body="x")
    path = v.resolve_wikilink("person-sarah-chen")
    assert path is not None and path.exists()


def test_resolve_wikilink_by_filename(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person(name="Sarah Chen"), body="x")
    path = v.resolve_wikilink("Sarah Chen")
    assert path is not None
    fm, _ = v.read_path(path)
    assert fm.id == "person-sarah-chen"


def test_write_to_inbox_when_low_confidence(tmp_vault: Path) -> None:
    v = Vault()
    note = _person()
    note = note.model_copy(update={"confidence": 0.5})
    v.write(note, body="x", route_low_confidence=True)
    inbox = list((tmp_vault / "90-Inbox").glob("*.md"))
    people = list((tmp_vault / "10-People").glob("*.md"))
    assert len(inbox) == 1 and len(people) == 0


def test_walk_yields_all(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_person("person-a", "A"), body="")
    v.write(_person("person-b", "B"), body="")
    ids = {n.id for n, _ in v.walk()}
    assert ids == {"person-a", "person-b"}
