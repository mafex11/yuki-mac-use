"""Per-task app-context injector.

Reads 40-Apps/<slug>.md notes for (a) the foreground app's bundle_id and
(b) any app whose name appears verbatim in the task text. Plus any
30-Routines/*.md whose frontmatter `apps` list contains a matched bundle_id.

Returns one concatenated string the /control router prepends as <app_context>.
"""

from __future__ import annotations

import re
from pathlib import Path

from yuki.memory import frontmatter as fm
from yuki.memory import paths


def _all_app_notes() -> list[tuple[str, str, str, Path]]:
    """Return [(bundle_id, name, body, path)] for every 40-Apps/*.md note."""
    apps_dir = paths.vault_dir() / "40-Apps"
    if not apps_dir.exists():
        return []
    out: list[tuple[str, str, str, Path]] = []
    for path in apps_dir.glob("*.md"):
        try:
            meta, body = fm.read_file(path)
        except Exception:
            continue
        if meta.get("type") != "app":
            continue
        bundle = str(meta.get("bundle_id") or "")
        name = str(meta.get("name") or path.stem)
        if bundle:
            out.append((bundle, name, body, path))
    return out


def _resolve_app_section(bundle_id: str) -> tuple[str, str] | None:
    for bundle, name, body, _ in _all_app_notes():
        if bundle == bundle_id:
            return name, body
    return None


def _apps_named_in_task(task_text: str) -> list[tuple[str, str, str]]:
    """Match apps whose `name` appears as a whole word in the task text.

    Case-insensitive. Returns [(bundle_id, name, body)] for each match.
    """
    if not task_text:
        return []
    text_lower = task_text.lower()
    matches: list[tuple[str, str, str]] = []
    for bundle, name, body, _ in _all_app_notes():
        n = name.strip().lower()
        if not n:
            continue
        if re.search(rf"\b{re.escape(n)}\b", text_lower):
            matches.append((bundle, name, body))
    return matches


def _matching_routines(bundle_id: str) -> list[tuple[str, str]]:
    routines_dir = paths.vault_dir() / "30-Routines"
    if not routines_dir.exists():
        return []
    out: list[tuple[str, str]] = []
    for path in routines_dir.glob("*.md"):
        try:
            meta, body = fm.read_file(path)
        except Exception:
            continue
        if meta.get("type") != "routine":
            continue
        apps = meta.get("apps") or []
        if isinstance(apps, list) and bundle_id in apps:
            name = str(meta.get("name") or path.stem)
            out.append((name, body))
    return out


def load_app_context(
    bundle_id: str,
    *,
    task_text: str = "",
    max_chars: int = 4000,
) -> str:
    """Return concatenated app notes + matching routines.

    Loads notes for: (a) the foreground bundle_id, (b) every app whose name
    appears in the task text. De-duplicates so a single app isn't loaded twice.
    Empty string when nothing matches. Output bounded by max_chars.
    """
    parts: list[str] = []
    seen_bundles: set[str] = set()
    bundle_ids_for_routines: list[str] = []

    if bundle_id:
        pair = _resolve_app_section(bundle_id)
        if pair is not None:
            name, body = pair
            parts.append(f"## App: {name} ({bundle_id})\n\n{body.strip()}\n")
            seen_bundles.add(bundle_id)
            bundle_ids_for_routines.append(bundle_id)

    for tb, tn, tbody in _apps_named_in_task(task_text):
        if tb in seen_bundles:
            continue
        parts.append(f"## App: {tn} ({tb})\n\n{tbody.strip()}\n")
        seen_bundles.add(tb)
        bundle_ids_for_routines.append(tb)

    seen_routines: set[str] = set()
    for bid in bundle_ids_for_routines:
        for name, body in _matching_routines(bid):
            key = f"{name}|{body[:50]}"
            if key in seen_routines:
                continue
            seen_routines.add(key)
            parts.append(f"## Routine: {name}\n\n{body.strip()}\n")

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
