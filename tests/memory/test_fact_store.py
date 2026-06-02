"""fact_store: flat fact view over the vault's personalization sections."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from yuki.memory import fact_store
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


def test_add_identity_fact_then_listed(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "I prefer dark mode everywhere")
    assert fact["section"] == "identity"
    assert fact["text"] == "I prefer dark mode everywhere"
    listed = fact_store.list_facts(v)
    assert any(f["id"] == fact["id"] for f in listed)


def test_add_identity_fact_slug_is_valid(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "Uses Linear for tickets!!!")
    # id is a lowercase kebab slug
    assert fact["id"]
    assert fact["id"] == fact["id"].lower()
    assert " " not in fact["id"]


def test_add_two_identical_texts_no_collision(tmp_vault: Path) -> None:
    v = Vault()
    a = fact_store.add_identity_fact(v, "Same text")
    b = fact_store.add_identity_fact(v, "Same text")
    assert a["id"] != b["id"]
    assert len(fact_store.list_facts(v)) == 2


def test_delete_fact_removes_it(tmp_vault: Path) -> None:
    v = Vault()
    fact = fact_store.add_identity_fact(v, "Delete me")
    assert fact_store.delete_fact(v, fact["id"]) is True
    assert all(f["id"] != fact["id"] for f in fact_store.list_facts(v))


def test_delete_missing_fact_returns_false(tmp_vault: Path) -> None:
    v = Vault()
    assert fact_store.delete_fact(v, "does-not-exist") is False


def test_title_consistent_between_add_and_list(tmp_vault: Path) -> None:
    v = Vault()
    added = fact_store.add_identity_fact(v, "I prefer dark mode everywhere")
    listed = next(f for f in fact_store.list_facts(v) if f["id"] == added["id"])
    assert added["title"] == listed["title"]
    assert added["text"] == listed["text"]
