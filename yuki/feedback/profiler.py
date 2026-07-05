"""Profiler — distill observer events into identity + routine notes.

The observer records what the user actually does (apps, window titles, music,
idle rhythm) into the local events table. This module is the missing link
that turns those raw events into the notes `load_hot_context` injects into
every chat/control call — i.e. how Yuki comes to know the user as a person.

Runs daily next to the app-note learner (yuki.feedback.cli). For each profile
aspect it aggregates the last N days of events IN CODE (compact counts, not
raw logs — only the aggregate ever reaches the LLM), asks the LLM for a short
distilled summary, and rewrites the auto-managed section of the matching
00-Identity / 30-Routines note. Human edits outside that section survive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from yuki.memory import frontmatter as fm
from yuki.memory import paths

log = logging.getLogger(__name__)

_AUTO_HEADER = "## Auto-learned"
_AUTO_RE = re.compile(rf"\n?{_AUTO_HEADER}\n.*?(?=\n## |\Z)", re.DOTALL)

# How many days of events feed one profile pass. A week smooths out one-off
# days; counts stay tiny because we aggregate before prompting.
_WINDOW_DAYS = 7

_MIN_EVENTS = 20  # below this the day is too thin to profile


# ---------------------------------------------------------------- aggregation

def _read_events(since: datetime) -> list[tuple[datetime, str, dict[str, Any]]]:
    db = paths.index_db_path()
    if not db.exists():
        return []
    out: list[tuple[datetime, str, dict[str, Any]]] = []
    conn = sqlite3.connect(db)
    try:
        cur = conn.execute(
            "SELECT ts, kind, payload FROM events WHERE ts >= ? ORDER BY ts",
            (int(since.timestamp() * 1000),),
        )
        for ts_ms, kind, payload in cur:
            try:
                out.append(
                    (
                        datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                        str(kind),
                        json.loads(payload or "{}"),
                    )
                )
            except Exception:
                continue
    finally:
        conn.close()
    return out


def _aggregate(events: list[tuple[datetime, str, dict[str, Any]]]) -> dict[str, Any]:
    """Compress raw events into the compact stats the LLM sees."""
    tracks: Counter[str] = Counter()
    artists: Counter[str] = Counter()
    apps: Counter[str] = Counter()
    titles_by_app: dict[str, Counter[str]] = {}
    hours_active: Counter[int] = Counter()

    for ts, kind, payload in events:
        local = ts.astimezone()
        if kind == "media_playing":
            track = payload.get("track", "")
            artist = payload.get("artist", "")
            if track:
                tracks[f"{track} — {artist}"] += 1
            if artist:
                artists[artist] += 1
        elif kind == "app_focus":
            app = payload.get("app", "")
            if app:
                apps[app] += 1
                hours_active[local.hour] += 1
        elif kind == "window_title":
            app = payload.get("app", "")
            title = payload.get("title", "")
            if app and title:
                titles_by_app.setdefault(app, Counter())[title] += 1
                hours_active[local.hour] += 1

    return {
        "top_artists": artists.most_common(15),
        "top_tracks": tracks.most_common(20),
        "top_apps": apps.most_common(15),
        # Browser/media titles reveal content taste (YouTube video titles show
        # up as window titles); cap per-app so one busy app can't flood.
        "sample_titles": {
            app: [t for t, _ in c.most_common(10)]
            for app, c in list(titles_by_app.items())[:10]
        },
        "active_hours": sorted(hours_active.items()),
    }


# ------------------------------------------------------------------- aspects

_ASPECTS: list[dict[str, str]] = [
    {
        "slug": "music-taste",
        "section": "00-Identity",
        "type": "identity",
        "name": "Music taste",
        "keys": "top_artists,top_tracks",
        "prompt": (
            "Summarize this user's music taste from their actual listening "
            "counts (last {days} days). Name the dominant genres/languages/"
            "moods you can infer, their most-played artists, and any patterns "
            "(e.g. J-pop while working). 3-6 bullets, each starting with '- '. "
            "Write about 'the user', concretely; no hedging filler."
        ),
    },
    {
        "slug": "content-interests",
        "section": "00-Identity",
        "type": "identity",
        "name": "Content interests",
        "keys": "sample_titles",
        "prompt": (
            "From these window titles (browser tabs, YouTube videos, documents "
            "— last {days} days), summarize what topics this user watches, "
            "reads, and works on. Group into themes (e.g. 'AI/programming "
            "tutorials', 'cooking videos'). 3-6 bullets, each starting with "
            "'- '. Skip anything that looks sensitive (health, finance, "
            "private conversations)."
        ),
    },
    {
        "slug": "app-habits",
        "section": "00-Identity",
        "type": "identity",
        "name": "App habits",
        "keys": "top_apps,sample_titles",
        "prompt": (
            "From these app-focus counts and window titles (last {days} days), "
            "describe how this user works on their Mac: primary apps and what "
            "they appear to use each for. 3-6 bullets, each starting with '- '."
        ),
    },
    {
        "slug": "daily-rhythm",
        "section": "30-Routines",
        "type": "routine",
        "name": "Daily rhythm",
        "keys": "active_hours,top_apps",
        "prompt": (
            "From these active-hour counts (hour-of-day → activity events, "
            "last {days} days), describe the user's daily rhythm: when they "
            "start, peak, break, and stop. 2-4 bullets, each starting with "
            "'- '. Hours are local time."
        ),
    },
]


def _summarize(aspect: dict[str, str], stats: dict[str, Any], days: int) -> str | None:
    from yuki.messages import HumanMessage
    from yuki.providers.factory import make_llm

    subset = {k: stats.get(k) for k in aspect["keys"].split(",")}
    if not any(subset.values()):
        return None
    try:
        llm = make_llm()
        prompt = (
            aspect["prompt"].format(days=days)
            + "\n\nData:\n"
            + json.dumps(subset, ensure_ascii=False, indent=1)
        )
        event = asyncio.run(
            llm.ainvoke(messages=[HumanMessage(content=prompt)], tools=[])
        )
        text = (event.content or "").strip() if event else ""
    except Exception as e:
        log.warning("profiler: LLM failed for %s: %s", aspect["slug"], e)
        return None
    # Require at least one bullet so a refusal/preamble never becomes a note.
    if "- " not in text:
        log.warning("profiler: malformed output for %s", aspect["slug"])
        return None
    return text


# --------------------------------------------------------------------- write

def _note_path(aspect: dict[str, str]) -> Path:
    return paths.vault_dir() / aspect["section"] / f"{aspect['slug']}.md"


def _write_note(aspect: dict[str, str], block: str, today: date) -> None:
    path = _note_path(aspect)
    auto = (
        f"\n{_AUTO_HEADER}\n\n"
        f"_Last updated: {today.isoformat()} (auto-managed -- do not edit)_\n\n"
        f"{block}\n"
    )
    if path.exists():
        meta, body = fm.read_file(path)
        if _AUTO_HEADER in body:
            body = _AUTO_RE.sub(auto, body, count=1)
        else:
            body = body.rstrip("\n") + "\n" + auto
        meta["updated_at"] = today.isoformat()
    else:
        meta = {
            "id": aspect["slug"],
            "type": aspect["type"],
            "name": aspect["name"],
            "created_at": today.isoformat(),
            "updated_at": today.isoformat(),
            "confidence": 0.6,
            "source": ["observer-profiler"],
        }
        if aspect["type"] == "routine":
            meta["schedule"] = "daily"
        body = auto
    path.parent.mkdir(parents=True, exist_ok=True)
    fm.write_file(path, meta, body)


# ---------------------------------------------------------------------- main

def run_profile(days: int = _WINDOW_DAYS) -> int:
    """Distill the last `days` of observer events into profile notes.

    Returns the number of notes updated. No events / thin data → 0, quietly.
    """
    since = datetime.now(UTC) - timedelta(days=days)
    events = _read_events(since)
    if len(events) < _MIN_EVENTS:
        log.info("profiler: only %d events in window; skipping", len(events))
        return 0
    stats = _aggregate(events)
    today = date.today()
    updated = 0
    for aspect in _ASPECTS:
        block = _summarize(aspect, stats, days)
        if block is None:
            continue
        try:
            _write_note(aspect, block, today)
            updated += 1
        except Exception as e:
            log.warning("profiler: write failed for %s: %s", aspect["slug"], e)
    return updated
