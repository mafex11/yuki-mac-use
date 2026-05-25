"""Pattern detector — Fact[] → Entity[].

Rule-based; deterministic. Each rule reads facts, produces 0..N entities.
Per spec §5.2: people, projects, routines, apps, identity.
"""

from __future__ import annotations

import re
from collections import defaultdict

from yuki.scan.entities import Entity
from yuki.scan.facts import Fact

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slug(prefix: str, name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return f"{prefix}-{s}" if s else prefix


def _build_alias_map(facts: list[Fact]) -> dict[str, str]:
    """email/handle → canonical name from contacts."""
    out: dict[str, str] = {}
    for f in facts:
        if f.predicate == "aliases_for":
            out[f.subject] = f.object
    return out


def _frequency(n: int) -> str:
    if n >= 10:
        return "daily"
    if n >= 4:
        return "weekly"
    if n >= 1:
        return "monthly"
    return "rare"


def _detect_people(facts: list[Fact], aliases: dict[str, str]) -> list[Entity]:
    contact_names = set(aliases.values())
    by_name: dict[str, list[Fact]] = defaultdict(list)
    for f in facts:
        if f.predicate in {"meets_with", "meets_with_recurring"}:
            by_name[f.subject].append(f)
        elif f.predicate == "emails_with":
            canonical = aliases.get(f.object)
            if canonical:
                by_name[canonical].append(f)

    out: list[Entity] = []
    for name, fs in by_name.items():
        if name not in contact_names and not any(f.predicate == "meets_with_recurring" for f in fs):
            continue
        recurring = sum(1 for f in fs if f.predicate == "meets_with_recurring")
        emails = sum(1 for f in fs if f.predicate == "emails_with")
        # Recurring meetings are strong signal — 0.3 per occurrence;
        # emails are weaker — 0.05 each.
        confidence = min(0.99, 0.6 + 0.3 * recurring + 0.05 * emails)
        out.append(
            Entity(
                kind="person",
                id=_slug("person", name),
                name=name,
                confidence=confidence,
                attributes={
                    "interaction_frequency": _frequency(recurring + emails),
                },
                fact_ids=[],
            )
        )
    return out


def _detect_projects(facts: list[Fact]) -> list[Entity]:
    out: list[Entity] = []
    for f in facts:
        if f.predicate == "works_on_project":
            out.append(
                Entity(
                    kind="project",
                    id=_slug("project", f.object),
                    name=f.object.title() if f.object.islower() else f.object,
                    confidence=f.confidence,
                    attributes={"status": "active"},
                    fact_ids=[],
                )
            )
    return out


def _detect_apps(facts: list[Fact]) -> list[Entity]:
    focus_counts: dict[str, int] = defaultdict(int)
    bundle_ids: dict[str, str] = {}
    seen_names: set[str] = set()

    for f in facts:
        if f.predicate == "uses_app":
            seen_names.add(f.object)

    for f in facts:
        if f.predicate == "focuses_on_app":
            name_guess = f.object.split(".")[-1].title()
            seen_names.add(name_guess)
            focus_counts[name_guess] += 1
            bundle_ids[name_guess] = f.object

    out: list[Entity] = []
    for name in seen_names:
        focus = focus_counts.get(name, 0)
        importance = "primary" if focus >= 1 else "occasional"
        out.append(
            Entity(
                kind="app",
                id=_slug("app", name),
                name=name,
                confidence=0.8 if focus else 0.55,
                attributes={
                    "bundle_id": bundle_ids.get(name, ""),
                    "importance": importance,
                },
                fact_ids=[],
            )
        )
    return out


def _detect_identity(facts: list[Fact]) -> list[Entity]:
    out: list[Entity] = []
    for f in facts:
        if f.predicate == "uses_machine":
            out.append(
                Entity(
                    kind="identity",
                    id="identity-profile",
                    name="Profile",
                    confidence=1.0,
                    attributes={"hostname": f.object},
                    fact_ids=[],
                )
            )
    return out


def detect(facts: list[Fact]) -> list[Entity]:
    aliases = _build_alias_map(facts)
    return [
        *_detect_identity(facts),
        *_detect_people(facts, aliases),
        *_detect_projects(facts),
        *_detect_apps(facts),
    ]
