"""fact_store: flat fact view over the vault's personalization sections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory.fact_store import list_facts
from yuki.memory.schemas import IdentityNote, PersonNote
from yuki.memory.vault import Vault


def _identity(id_: str, name: str, body: str) -> IdentityNote:
    now = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    return IdentityNote(
        id=id_, type="identity", created_at=now, updated_at=now,
        confidence=0.9, source=["user"], name=name, body=body,
    )


def _person(id_: str, name: str) -> PersonNote:
    now = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    return PersonNote(
        id=id_, type="person", created_at=now, updated_at=now,
        confidence=0.9, source=["user"], name=name,
    )


def test_list_facts_groups_by_section(tmp_vault: Path) -> None:
    v = Vault()
    v.write(_identity("builds-mac-apps", "builds mac apps",
                      "Builds native Mac apps; prefers concise answers."), body="")
    v.write(_person("person-saran", "Saran"), body="Friend on WhatsApp.")

    facts = list_facts(v)

    ids = {f["id"] for f in facts}
    assert "builds-mac-apps" in ids
    assert "person-saran" in ids
    identity = next(f for f in facts if f["id"] == "builds-mac-apps")
    assert identity["section"] == "identity"
    person = next(f for f in facts if f["id"] == "person-saran")
    assert person["section"] == "people"
    # each fact has display text
    assert identity["text"]
    assert person["text"]
