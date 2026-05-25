"""Normalizer — raw collector JSON → Fact tuples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from yuki.scan.normalizer import normalize


def _write(cache: Path, name: str, data: list[dict[str, Any]]) -> None:
    raw = cache / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{name}.json").write_text(json.dumps(data))


def test_apps_become_uses_app_facts(tmp_scan_cache: Path) -> None:
    _write(
        tmp_scan_cache,
        "apps",
        [
            {"name": "Slack", "bundle_id": "com.tinyspeck.slackmacgap", "path": "/x"},
            {"name": "Vim", "bundle_id": "org.vim.MacVim", "path": "/y"},
        ],
    )
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("user", "uses_app", "Slack") in triples
    assert ("user", "uses_app", "Vim") in triples


def test_calendar_recurring_with_attendees_yields_meets_with(
    tmp_scan_cache: Path,
) -> None:
    _write(
        tmp_scan_cache,
        "calendar",
        [
            {
                "title": "1:1",
                "organizer": "Sarah Chen",
                "attendees": ["user", "Sarah Chen"],
                "start": "2026-05-01T10:00:00+00:00",
                "recurring": True,
            }
        ],
    )
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("Sarah Chen", "meets_with_recurring", "user") in triples


def test_mail_top_senders(tmp_scan_cache: Path) -> None:
    _write(
        tmp_scan_cache,
        "mail",
        [
            {"address": "sarah@example.com", "count": 30, "last_seen_unix": 1700000000},
            {"address": "sarah@example.com", "count": 30, "last_seen_unix": 1700000000},
        ],
    )
    facts = normalize()
    triples = {(f.subject, f.predicate, f.object) for f in facts}
    assert ("user", "emails_with", "sarah@example.com") in triples


def test_git_emits_works_on_project(tmp_scan_cache: Path) -> None:
    _write(
        tmp_scan_cache,
        "git",
        [
            {
                "name": "yuki",
                "path": "/Users/me/code/yuki",
                "last_commit": "2026-05-22T08:00:00+00:00",
                "commit_count": 50,
                "recent_subjects": ["init"],
            }
        ],
    )
    facts = normalize()
    assert any(f.predicate == "works_on_project" and f.object == "yuki" for f in facts)


def test_missing_cache_returns_empty(tmp_scan_cache: Path) -> None:
    assert normalize() == []
