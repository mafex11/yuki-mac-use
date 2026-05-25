"""Builder — events → daily episode markdown in 60-Episodes/."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from yuki.episodist.labeler import label
from yuki.episodist.reader import read_events_for_date
from yuki.episodist.sessions import segment
from yuki.memory import paths
from yuki.observer.events import Event

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(disabled_extensions=("md.j2",)),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _bullets(events: list[Event]) -> list[str]:
    out: list[str] = []
    titles_seen: set[str] = set()
    for e in events:
        if e.kind.value == "window_title":
            t = str(e.payload.get("title", "")).strip()
            if t and t not in titles_seen:
                titles_seen.add(t)
                out.append(t)
    return out[:5]


def build_for_date(d: date) -> Path:
    events = read_events_for_date(d)
    sessions = segment(events, gap_minutes=5)
    rows: list[dict[str, object]] = []
    for s in sessions:
        rows.append(
            {
                "start_h": s.start.hour,
                "start_m": s.start.minute,
                "end_h": s.end.hour,
                "end_m": s.end.minute,
                "label": label(s),
                "bullets": _bullets(s.events),
            }
        )
    template = _env.get_template("episode.md.j2")
    text = template.render(
        date=d.isoformat(),
        now=datetime.now(UTC).isoformat(),
        sessions=rows,
    )
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{d.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    return path
