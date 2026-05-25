"""Pattern detector — Fact[] → Entity[]."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from yuki.scan.facts import Fact
from yuki.scan.patterns import detect


def _f(
    subject: str,
    predicate: str,
    object_: str,
    sources: Sequence[str],
    confidence: float = 0.8,
) -> Fact:
    now = datetime(2026, 5, 22, tzinfo=UTC)
    return Fact(
        subject=subject,
        predicate=predicate,
        object=object_,
        confidence=confidence,
        sources=list(sources),
        evidence=[{}],
        first_seen=now,
        last_seen=now,
    )


def test_recurring_meeting_plus_contact_yields_person() -> None:
    facts = [
        _f("Sarah Chen", "meets_with_recurring", "user", ["calendar"]),
        _f("sarah@x.com", "aliases_for", "Sarah Chen", ["contacts"]),
    ]
    entities = detect(facts)
    persons = [e for e in entities if e.kind == "person"]
    assert len(persons) == 1
    assert persons[0].name == "Sarah Chen"
    assert persons[0].confidence > 0.85


def test_app_high_focus_yields_primary() -> None:
    facts = [
        _f("user", "uses_app", "Slack", ["apps"]),
        _f(
            "user",
            "focuses_on_app",
            "com.tinyspeck.slackmacgap",
            ["screen_time"],
            0.9,
        ),
    ]
    entities = detect(facts)
    apps = [e for e in entities if e.kind == "app"]
    assert any(a.name == "Slack" for a in apps)


def test_git_repo_yields_project() -> None:
    facts = [_f("user", "works_on_project", "yuki", ["git"])]
    entities = detect(facts)
    projects = [e for e in entities if e.kind == "project"]
    assert len(projects) == 1
    assert projects[0].name in {"Yuki", "yuki"}


def test_no_facts_yields_no_entities() -> None:
    assert detect([]) == []


def test_email_without_contact_does_not_create_person() -> None:
    facts = [_f("user", "emails_with", "newsletter@spam.test", ["mail"])]
    entities = detect(facts)
    assert all(e.kind != "person" for e in entities)
