"""Fact-oriented view over the vault's personalization sections.

The vault stores strongly-typed notes; this module flattens the four
user-facing personalization sections into simple {id, section, title, text}
"facts" for the Memory UI and slash commands. Writing is limited to free-text
IdentityNotes (see add_identity_fact) because the other note types have
required structured fields the UI doesn't collect.
"""

from __future__ import annotations

from typing import TypedDict

from yuki.memory.schemas import AnyNote
from yuki.memory.vault import Vault

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
