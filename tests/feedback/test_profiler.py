"""Profiler: events → aggregate → note writing (LLM stubbed)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yuki.feedback import profiler
from yuki.memory import frontmatter as fm


def _seed_events(db_path: Path, n_tracks: int = 10) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS events (ts INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT)"
    )
    now = datetime.now(UTC)
    rows = []
    for i in range(n_tracks):
        ts = int((now - timedelta(hours=i)).timestamp() * 1000)
        rows.append(
            (ts, "media_playing",
             json.dumps({"player": "Spotify", "track": f"track{i % 3}",
                         "artist": "YOASOBI", "album": "THE BOOK"}))
        )
        rows.append(
            (ts, "app_focus", json.dumps({"app": "Google Chrome"}))
        )
        rows.append(
            (ts, "window_title",
             json.dumps({"app": "Google Chrome",
                         "title": "ML tutorial - YouTube"}))
        )
    conn.executemany("INSERT INTO events(ts, kind, payload) VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()


def test_aggregate_counts_media_and_apps(tmp_vault: Path, tmp_path: Path) -> None:
    _seed_events(tmp_path / "index.db")
    events = profiler._read_events(datetime.now(UTC) - timedelta(days=7))
    stats = profiler._aggregate(events)
    assert stats["top_artists"][0][0] == "YOASOBI"
    assert stats["top_apps"][0][0] == "Google Chrome"
    assert "Google Chrome" in stats["sample_titles"]


def test_run_profile_writes_notes(
    tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_events(tmp_path / "index.db")
    monkeypatch.setattr(
        profiler, "_summarize",
        lambda aspect, stats, days: "- listens to J-pop daily\n- YOASOBI on repeat",
    )
    updated = profiler.run_profile()
    assert updated == len(profiler._ASPECTS)

    note = tmp_vault / "00-Identity" / "music-taste.md"
    assert note.exists()
    meta, body = fm.read_file(note)
    assert meta["type"] == "identity"
    assert "## Auto-learned" in body
    assert "J-pop" in body

    routine = tmp_vault / "30-Routines" / "daily-rhythm.md"
    assert routine.exists()
    rmeta, _ = fm.read_file(routine)
    assert rmeta["type"] == "routine" and rmeta["schedule"] == "daily"


def test_rerun_replaces_auto_section_preserves_manual(
    tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_events(tmp_path / "index.db")
    monkeypatch.setattr(
        profiler, "_summarize", lambda a, s, d: "- first pass"
    )
    profiler.run_profile()

    # A human adds a manual section above the auto block.
    note = tmp_vault / "00-Identity" / "music-taste.md"
    meta, body = fm.read_file(note)
    fm.write_file(note, meta, "## My notes\n\nhand-written\n" + body)

    monkeypatch.setattr(
        profiler, "_summarize", lambda a, s, d: "- second pass"
    )
    profiler.run_profile()
    _, body2 = fm.read_file(note)
    assert "hand-written" in body2
    assert "second pass" in body2
    assert "first pass" not in body2
    assert body2.count("## Auto-learned") == 1


def test_thin_data_skips(tmp_vault: Path, tmp_path: Path) -> None:
    # No events table at all → 0 notes, no crash.
    assert profiler.run_profile() == 0


def test_profile_notes_flow_into_hot_context(
    tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: profiler output must reach the agent's context."""
    _seed_events(tmp_path / "index.db")
    monkeypatch.setattr(
        profiler, "_summarize",
        lambda a, s, d: "- loves J-pop, especially YOASOBI",
    )
    profiler.run_profile()

    from yuki.memory import load_hot_context
    from yuki.memory.vault import Vault

    hot = load_hot_context(Vault(root=tmp_vault))
    assert "YOASOBI" in hot
    assert "Music taste" in hot


def test_malformed_llm_output_is_rejected(
    tmp_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_events(tmp_path / "index.db")

    class _Ev:
        content = "I cannot determine the user's taste from this data."

    class _LLM:
        async def ainvoke(self, messages, tools):
            return _Ev()

    monkeypatch.setattr(
        "yuki.providers.factory.make_llm", lambda *a, **k: _LLM()
    )
    assert profiler.run_profile() == 0
