"""Notewriter — Entity → markdown via Jinja templates → vault."""

from __future__ import annotations

from pathlib import Path

from yuki.memory.schemas import AppNote, PersonNote, ProjectNote
from yuki.memory.vault import Vault
from yuki.scan.entities import Entity
from yuki.scan.notewriter import write_entities


def test_writes_person_note(tmp_vault: Path) -> None:
    e = Entity(
        kind="person",
        id="person-sarah-chen",
        name="Sarah Chen",
        confidence=0.92,
        attributes={"role": "manager", "interaction_frequency": "weekly"},
        fact_ids=[],
    )
    v = Vault()
    written = write_entities([e], vault=v, sources=["calendar"])
    assert len(written) == 1
    note, body = v.read("person-sarah-chen")
    assert isinstance(note, PersonNote)
    assert note.name == "Sarah Chen"
    assert "Sarah Chen" in body


def test_writes_project_note(tmp_vault: Path) -> None:
    e = Entity(
        kind="project",
        id="project-yuki",
        name="Yuki",
        confidence=0.85,
        attributes={
            "status": "active",
            "tech": ["python"],
            "path": "/Users/me/code/yuki",
        },
        fact_ids=[],
    )
    v = Vault()
    write_entities([e], vault=v, sources=["git"])
    note, _ = v.read("project-yuki")
    assert isinstance(note, ProjectNote)
    assert note.status == "active"


def test_writes_app_note(tmp_vault: Path) -> None:
    e = Entity(
        kind="app",
        id="app-slack",
        name="Slack",
        confidence=0.85,
        attributes={
            "bundle_id": "com.tinyspeck.slackmacgap",
            "importance": "primary",
        },
        fact_ids=[],
    )
    v = Vault()
    write_entities([e], vault=v, sources=["apps", "screen_time"])
    note, _ = v.read("app-slack")
    assert isinstance(note, AppNote)
    assert note.importance == "primary"


def test_writes_identity_note(tmp_vault: Path) -> None:
    e = Entity(
        kind="identity",
        id="identity-profile",
        name="Profile",
        confidence=1.0,
        attributes={"hostname": "my-mac.local"},
        fact_ids=[],
    )
    v = Vault()
    write_entities([e], vault=v, sources=["system"])
    _, body = v.read("identity-profile")
    assert "my-mac.local" in body


def test_skips_unsupported_kind(tmp_vault: Path) -> None:
    e = Entity(
        kind="routine",
        id="routine-x",
        name="X",
        confidence=0.5,
        attributes={"schedule": "??", "steps": []},
        fact_ids=[],
    )
    v = Vault()
    written = write_entities([e], vault=v, sources=[])
    assert written == []
