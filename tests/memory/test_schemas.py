"""Pydantic note-schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from yuki.memory.schemas import (
    AppNote,
    PersonNote,
    ProjectNote,
    RoutineNote,
    TriggerNote,
    parse_note,
)


def _common() -> dict[str, object]:
    return {
        "id": "person-sarah-chen",
        "type": "person",
        "created_at": "2026-05-22T09:00:00Z",
        "updated_at": "2026-05-22T09:00:00Z",
        "confidence": 0.92,
        "source": ["calendar", "contacts"],
    }


def test_person_minimal() -> None:
    data = _common() | {"name": "Sarah Chen"}
    note = parse_note(data)
    assert isinstance(note, PersonNote)
    assert note.name == "Sarah Chen"
    assert note.relationship is None


def test_person_full() -> None:
    data = _common() | {
        "name": "Sarah Chen",
        "role": "Engineering Manager",
        "relationship": "manager",
        "contact": {"email": "sarah@example.com", "slack": "sarah"},
        "last_seen": "2026-05-21T15:00:00Z",
        "interaction_frequency": "daily",
    }
    note = parse_note(data)
    assert isinstance(note, PersonNote)
    assert note.relationship == "manager"
    assert note.contact.email == "sarah@example.com"


def test_project_note() -> None:
    data = {
        **_common(),
        "id": "project-yuki",
        "type": "project",
        "name": "Yuki",
        "status": "active",
        "tech": ["python", "swift"],
        "path": "/Users/me/code/yuki",
        "last_touched": "2026-05-22T08:00:00Z",
    }
    note = parse_note(data)
    assert isinstance(note, ProjectNote)
    assert note.status == "active"


def test_routine_note() -> None:
    data = {
        **_common(),
        "id": "routine-morning",
        "type": "routine",
        "name": "Morning",
        "schedule": "weekdays 8am",
        "steps": ["[[Coffee]]", "[[Email Triage]]"],
        "trusted": False,
    }
    note = parse_note(data)
    assert isinstance(note, RoutineNote)
    assert note.trusted is False
    assert len(note.steps) == 2


def test_app_note() -> None:
    data = {
        **_common(),
        "id": "app-slack",
        "type": "app",
        "name": "Slack",
        "bundle_id": "com.tinyspeck.slackmacgap",
        "importance": "primary",
        "common_uses": ["team chat"],
    }
    note = parse_note(data)
    assert isinstance(note, AppNote)
    assert note.importance == "primary"


def test_trigger_note() -> None:
    data = {
        **_common(),
        "id": "trigger-standup-reminder",
        "type": "trigger",
        "enabled": True,
        "condition": {"kind": "time", "cron": "0 10 * * 1-5"},
        "debounce": "1h",
        "action": {"kind": "suggestion", "text": "Standup in 5"},
        "last_fired": None,
        "fire_count": 0,
        "acceptance_rate": 0.0,
    }
    note = parse_note(data)
    assert isinstance(note, TriggerNote)
    assert note.enabled is True


def test_invalid_type_rejected() -> None:
    data = _common() | {"type": "alien", "name": "x"}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_confidence_out_of_range() -> None:
    data = _common() | {"name": "x", "confidence": 1.5}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_id_must_be_slug() -> None:
    data = _common() | {"name": "x", "id": "Has Spaces"}
    with pytest.raises(ValidationError):
        parse_note(data)


def test_anynote_round_trip() -> None:
    data = _common() | {"name": "Sarah Chen"}
    note = parse_note(data)
    dumped = note.model_dump(mode="json")
    again = parse_note(dumped)
    assert again == note
