"""Normalizer — raw collector JSON → unified Fact tuples."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from yuki.scan import paths
from yuki.scan.facts import Fact, dedupe


def _now() -> datetime:
    return datetime.now(UTC)


def _load(name: str) -> list[dict[str, Any]]:
    p = paths.raw_path(name)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return []


def _from_apps(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="uses_app",
            object=r["name"],
            confidence=0.6,
            sources=["apps"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("name")
    ]


def _from_calendar(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    out: list[Fact] = []
    for r in rows:
        attendees = [a for a in (r.get("attendees") or []) if a and a != "user"]
        if not attendees:
            continue
        predicate = "meets_with_recurring" if r.get("recurring") else "meets_with"
        for person in attendees:
            out.append(
                Fact(
                    subject=person,
                    predicate=predicate,
                    object="user",
                    confidence=0.85 if r.get("recurring") else 0.55,
                    sources=["calendar"],
                    evidence=[r],
                    first_seen=now,
                    last_seen=now,
                )
            )
    return out


def _from_contacts(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    out: list[Fact] = []
    for r in rows:
        full = f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
        if not full:
            continue
        for email in r.get("emails", []):
            out.append(
                Fact(
                    subject=email,
                    predicate="aliases_for",
                    object=full,
                    confidence=0.95,
                    sources=["contacts"],
                    evidence=[r],
                    first_seen=now,
                    last_seen=now,
                )
            )
    return out


def _from_mail(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="emails_with",
            object=r["address"],
            confidence=min(0.95, 0.4 + r.get("count", 0) / 100),
            sources=["mail"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("address")
    ]


def _from_git(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="works_on_project",
            object=r["name"],
            confidence=min(0.95, 0.5 + r.get("commit_count", 0) / 100),
            sources=["git"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("name")
    ]


def _from_browser(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="visits_domain",
            object=r["domain"],
            confidence=min(0.95, 0.4 + r.get("visits", 0) / 200),
            sources=["browser"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("domain")
    ]


def _from_screen_time(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="focuses_on_app",
            object=r["bundle_id"],
            confidence=0.8,
            sources=["screen_time"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("bundle_id")
    ]


def _from_shell(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="runs_command",
            object=r["command"],
            confidence=min(0.95, 0.3 + r.get("count", 0) / 50),
            sources=["shell"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("command")
    ]


def _from_files(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    return [
        Fact(
            subject="user",
            predicate="active_in_directory",
            object=r["directory"],
            confidence=min(0.95, 0.3 + r.get("count", 0) / 30),
            sources=["files"],
            evidence=[r],
            first_seen=now,
            last_seen=now,
        )
        for r in rows
        if r.get("directory")
    ]


def _from_system(rows: list[dict[str, Any]]) -> list[Fact]:
    now = _now()
    out: list[Fact] = []
    for r in rows:
        if r.get("hostname"):
            out.append(
                Fact(
                    subject="user",
                    predicate="uses_machine",
                    object=r["hostname"],
                    confidence=1.0,
                    sources=["system"],
                    evidence=[r],
                    first_seen=now,
                    last_seen=now,
                )
            )
    return out


_HANDLERS: dict[str, Callable[[list[dict[str, Any]]], list[Fact]]] = {
    "apps": _from_apps,
    "calendar": _from_calendar,
    "contacts": _from_contacts,
    "mail": _from_mail,
    "git": _from_git,
    "browser": _from_browser,
    "screen_time": _from_screen_time,
    "shell": _from_shell,
    "files": _from_files,
    "system": _from_system,
}


def normalize() -> list[Fact]:
    facts: list[Fact] = []
    for name, handler in _HANDLERS.items():
        facts.extend(handler(_load(name)))
    return dedupe(facts)
