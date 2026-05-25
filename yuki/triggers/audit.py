"""Audit log — append fired suggestions to 60-Episodes/triggers-YYYY-MM-DD.md."""

from __future__ import annotations

from yuki.memory import paths
from yuki.triggers.presenter import Suggestion


def append_to_audit(suggestion: Suggestion, *, accepted: bool) -> None:
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    day = suggestion.ts.date().isoformat()
    path = out_dir / f"triggers-{day}.md"
    state = "accepted" if accepted else "dismissed"
    line = (
        f"- {suggestion.ts.isoformat()} | {suggestion.trigger_id} | "
        f"{suggestion.urgency} | {state} | {suggestion.text}\n"
    )
    if not path.exists():
        path.write_text(f"# Trigger audit — {day}\n\n{line}", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
