"""Learner auto-creates skeleton 40-Apps notes for apps seen often enough."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from yuki.feedback import learner
from yuki.memory import frontmatter as fm

_BLOCK = (
    "### Confirmed working\n- cmd+f opens search\n\n"
    "### Avoid\n- (none)"
)


def _record(task: str, bundle_ids: list[str], outcome: str = "success") -> dict:
    return {
        "task": task,
        "conversation_id": "c1",
        "started_at": "2026-07-04T10:00:00",
        "duration_s": 5.0,
        "steps_used": 3,
        "outcome": outcome,
        "apps_involved": bundle_ids,
        "actions": [],
        "failure_mode": "null",
        "recovery_attempts": 0,
    }


def _write_day(vault: Path, day: date, records: list[dict]) -> None:
    body = yaml.safe_dump(records, sort_keys=False, allow_unicode=True)
    path = vault / "60-Episodes" / f"control-{day.isoformat()}.md"
    path.write_text(
        f"# /control task records -- {day.isoformat()}\n\n```yaml\n{body}```\n",
        encoding="utf-8",
    )


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        learner, "_summarize_via_llm", lambda app_name, bundle_id, recs: _BLOCK
    )


def test_note_created_when_two_records(
    tmp_vault: Path, stub_llm: None
) -> None:
    day = date(2026, 7, 4)
    _write_day(
        tmp_vault,
        day,
        [
            _record("play music", ["com.spotify.client"]),
            _record("pause music", ["com.spotify.client"], outcome="failure"),
        ],
    )

    assert learner.run_for_date(day) == 1

    note = tmp_vault / "40-Apps" / "Spotify.md"
    assert note.exists()
    meta, body = fm.read_file(note)
    assert meta["id"] == "app-spotify"
    assert meta["type"] == "app"
    assert meta["name"] == "Spotify"
    assert meta["bundle_id"] == "com.spotify.client"
    assert meta["importance"] == "occasional"
    assert meta["common_uses"] == []
    assert meta["confidence"] == 0.5
    assert meta["created_at"] == date.today().isoformat()
    assert meta["updated_at"] == date.today().isoformat()
    assert body.count("## Auto-learned") == 1
    assert "cmd+f opens search" in body


def test_note_not_created_for_single_record(
    tmp_vault: Path, stub_llm: None
) -> None:
    day = date(2026, 7, 4)
    _write_day(tmp_vault, day, [_record("play music", ["com.spotify.client"])])

    assert learner.run_for_date(day) == 0
    assert not list((tmp_vault / "40-Apps").glob("*.md"))


def test_existing_note_untouched_by_creation_path(
    tmp_vault: Path, stub_llm: None
) -> None:
    """Creating a skeleton for a new app must not disturb existing notes."""
    existing = tmp_vault / "40-Apps" / "WhatsApp.md"
    fm.write_file(
        existing,
        {
            "id": "app-whatsapp",
            "type": "app",
            "name": "WhatsApp",
            "bundle_id": "net.whatsapp.WhatsApp",
            "importance": "primary",
            "common_uses": ["messaging"],
            "created_at": "2026-05-31",
            "updated_at": "2026-05-31",
            "confidence": 0.9,
        },
        "Hand-written guidance that must survive.\n",
    )

    day = date(2026, 7, 4)
    _write_day(
        tmp_vault,
        day,
        [
            _record("msg saran", ["net.whatsapp.WhatsApp"]),
            _record("msg mom", ["net.whatsapp.WhatsApp"]),
            _record("open slack", ["com.tinyspeck.slackmacgap"]),
            _record("reply on slack", ["com.tinyspeck.slackmacgap"]),
        ],
    )

    # Both the existing WhatsApp note (update path) and the new Slack
    # skeleton (creation path) count.
    assert learner.run_for_date(day) == 2

    # WhatsApp: hand-written part preserved, auto section appended.
    meta, body = fm.read_file(existing)
    assert meta["name"] == "WhatsApp"
    assert meta["importance"] == "primary"
    assert "Hand-written guidance that must survive." in body
    assert body.count("## Auto-learned") == 1

    # Slack skeleton created alongside, without clobbering anything.
    slack = tmp_vault / "40-Apps" / "Slack.md"
    assert slack.exists()
    smeta, _ = fm.read_file(slack)
    assert smeta["bundle_id"] == "com.tinyspeck.slackmacgap"
    assert smeta["name"] == "Slack"


def test_creation_skipped_on_filename_collision(
    tmp_vault: Path, stub_llm: None
) -> None:
    """A same-named note for a different bundle id must not be clobbered."""
    other = tmp_vault / "40-Apps" / "Spotify.md"
    fm.write_file(
        other,
        {"id": "app-spotify", "type": "app", "name": "Spotify",
         "bundle_id": "com.other.spotify-fork"},
        "Different app, same name.\n",
    )

    day = date(2026, 7, 4)
    _write_day(
        tmp_vault,
        day,
        [
            _record("play", ["com.spotify.client"]),
            _record("pause", ["com.spotify.client"]),
        ],
    )
    assert learner.run_for_date(day) == 0
    _, body = fm.read_file(other)
    assert "Different app, same name." in body
    assert "## Auto-learned" not in body


def test_derive_app_name() -> None:
    assert learner.derive_app_name("net.whatsapp.WhatsApp") == "WhatsApp"
    assert learner.derive_app_name("com.spotify.client") == "Spotify"
    assert learner.derive_app_name("com.google.Chrome") == "Google Chrome"
    assert learner.derive_app_name("com.tinyspeck.slackmacgap") == "Slack"
    # Unknown bundles: last component, title-cased when all-lowercase.
    assert learner.derive_app_name("com.example.notion") == "Notion"
    assert learner.derive_app_name("com.apple.Safari") == "Safari"
    assert learner.derive_app_name("org.mozilla.firefox") == "Firefox"
