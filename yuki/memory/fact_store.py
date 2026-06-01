"""Fact-oriented view over the vault's personalization sections.

The vault stores strongly-typed notes; this module flattens the four
user-facing personalization sections into simple {id, section, title, text}
"facts" for the Memory UI and slash commands. Writing is limited to free-text
IdentityNotes (see add_identity_fact) because the other note types have
required structured fields the UI doesn't collect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from yuki.memory.schemas import AnyNote, IdentityNote
from yuki.memory.vault import Vault, slugify

# vault section dir -> stable UI key
_SECTION_KEYS: dict[str, str] = {
    "00-Identity": "identity",
    "10-People": "people",
    "20-Projects": "projects",
    "40-Apps": "apps",
}


class Fact(TypedDict):
    id: str
    section: str
    title: str
    text: str


def _display_text(note: AnyNote, body: str) -> str:
    """Human-readable one-liner for a note."""
    body = (body or "").strip()
    if body:
        return body
    # Fall back to a structured summary when there's no body.
    name = getattr(note, "name", note.id)
    extra = getattr(note, "value", None) or getattr(note, "role", None) or ""
    return f"{name} — {extra}".strip(" —") or name


def list_facts(vault: Vault) -> list[Fact]:
    """All personalization facts across Identity/People/Projects/Apps."""
    out: list[Fact] = []
    for section, key in _SECTION_KEYS.items():
        for note, body in vault.list_section(section):
            title = getattr(note, "name", note.id)
            out.append(
                Fact(id=note.id, section=key, title=title,
                     text=_display_text(note, body))
            )
    return out


def _unique_id(vault: Vault, base: str) -> str:
    """A valid, collision-free kebab-case id derived from base text."""
    slug = slugify(base).lower() or "fact"
    slug = slug[:48].strip("-") or "fact"
    if vault.resolve_wikilink(slug) is None:
        return slug
    n = 2
    while vault.resolve_wikilink(f"{slug}-{n}") is not None:
        n += 1
    return f"{slug}-{n}"


def add_identity_fact(vault: Vault, text: str) -> Fact:
    """Write a free-text fact as an IdentityNote. Text lives in the body."""
    text = text.strip()
    now = datetime.now(UTC)
    id_ = _unique_id(vault, text)
    note = IdentityNote(
        id=id_,
        type="identity",
        created_at=now,
        updated_at=now,
        confidence=0.9,
        source=["user"],
        name=id_,  # Use id as name to ensure unique filenames
        body=text,
    )
    vault.write(note, body=text)
    return Fact(id=note.id, section="identity", title=text[:60] or "fact", text=text)


def delete_fact(vault: Vault, fact_id: str) -> bool:
    """Remove a fact's note by id. Returns False if not found."""
    path = vault.resolve_wikilink(fact_id)
    if path is None:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True
