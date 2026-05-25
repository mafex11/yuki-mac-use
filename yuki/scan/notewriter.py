"""Notewriter — Entity[] → markdown notes in the vault."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from yuki.memory.schemas import (
    AnyNote,
    AppNote,
    IdentityNote,
    PersonContact,
    PersonNote,
    ProjectNote,
)
from yuki.memory.vault import Vault
from yuki.scan.entities import Entity

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("md.j2",)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _build_person(e: Entity, sources: list[str]) -> PersonNote:
    now = _now()
    relationship = e.attributes.get("relationship")
    return PersonNote(
        id=e.id,
        type="person",
        created_at=now,
        updated_at=now,
        confidence=e.confidence,
        source=sources,
        name=e.name,
        role=e.attributes.get("role"),
        relationship=relationship,
        contact=PersonContact(),
        interaction_frequency=e.attributes.get("interaction_frequency"),
    )


def _build_project(e: Entity, sources: list[str]) -> ProjectNote:
    now = _now()
    return ProjectNote(
        id=e.id,
        type="project",
        created_at=now,
        updated_at=now,
        confidence=e.confidence,
        source=sources,
        name=e.name,
        status=e.attributes.get("status", "active"),
        tech=e.attributes.get("tech", []),
        path=e.attributes.get("path"),
    )


def _build_app(e: Entity, sources: list[str]) -> AppNote:
    now = _now()
    return AppNote(
        id=e.id,
        type="app",
        created_at=now,
        updated_at=now,
        confidence=e.confidence,
        source=sources,
        name=e.name,
        bundle_id=e.attributes.get("bundle_id", ""),
        importance=e.attributes.get("importance", "occasional"),
        common_uses=e.attributes.get("common_uses", []),
    )


def _build_identity(e: Entity, sources: list[str]) -> IdentityNote:
    now = _now()
    return IdentityNote(
        id=e.id,
        type="identity",
        created_at=now,
        updated_at=now,
        confidence=e.confidence,
        source=sources,
        name=e.name,
        body="",
    )


_BUILDERS: dict[str, Callable[[Entity, list[str]], AnyNote]] = {
    "person": _build_person,
    "project": _build_project,
    "app": _build_app,
    "identity": _build_identity,
}


def write_entities(
    entities: list[Entity],
    *,
    vault: Vault,
    sources: list[str],
) -> list[Path]:
    written: list[Path] = []
    for e in entities:
        builder = _BUILDERS.get(e.kind)
        if builder is None:
            continue
        note = builder(e, sources)
        template = _env.get_template(f"{e.kind}.md.j2")
        body = template.render(name=e.name, attributes=e.attributes, sources=sources)
        path = vault.write(note, body)
        written.append(path)
    return written
