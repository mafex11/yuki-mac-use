"""Action audit — append every executed tool call to a daily episode file."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from yuki.memory import paths


def append_action_audit(
    *,
    tool_name: str,
    args: dict[str, Any],
    danger: str,
    reason: str,
    ts: datetime,
) -> None:
    out_dir = paths.vault_dir() / "60-Episodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    day = ts.date().isoformat()
    path = out_dir / f"actions-{day}.md"
    line = (
        f"- {ts.isoformat()} | {tool_name} | {danger} | {reason} | "
        f"{json.dumps(args, default=str)}\n"
    )
    if not path.exists():
        path.write_text(f"# Action audit — {day}\n\n{line}", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
