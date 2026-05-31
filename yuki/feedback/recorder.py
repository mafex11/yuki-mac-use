"""Per-task structured recorder.

Appends YAML records to 60-Episodes/control-YYYY-MM-DD.md after each /control
task. Pure deterministic Python -- no LLM. Reuses the trajectory redactor
(Plan I) to scrub secrets before writing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from yuki.backend.trajectory import _redact
from yuki.memory import paths


class FailureMode(StrEnum):
    NONE = "null"
    WRONG_COORDS = "wrong_coords"
    ELEMENT_NOT_FOCUSED = "element_not_focused"
    TOOL_VALIDATION_ERROR = "tool_validation_error"
    LOOP_3_STRIKES = "loop_3_strikes"
    AGENT_STEP_LIMIT = "agent_step_limit"
    PROVIDER_ERROR = "provider_error"


@dataclass
class ActionTrace:
    tool: str
    params: dict[str, Any]
    result: str  # "success" | "failure"
    ax_window_before: str | None = None
    ax_window_after: str | None = None
    ax_focused_before: str | None = None
    ax_focused_after: str | None = None
    ax_value_after: str | None = None


@dataclass
class TaskRecord:
    task: str
    conversation_id: str
    started_at: datetime
    duration_s: float
    steps_used: int
    outcome: str  # "success" | "failure" | "partial"
    apps_involved: list[str]
    actions: list[ActionTrace] = field(default_factory=list)
    failure_mode: FailureMode = FailureMode.NONE
    recovery_attempts: int = 0


def _path_for(day: datetime) -> Path:
    return paths.vault_dir() / "60-Episodes" / f"control-{day.date().isoformat()}.md"


def _existing_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "```yaml" not in text:
        return []
    body = text.split("```yaml", 1)[1].split("```", 1)[0]
    parsed = yaml.safe_load(body) or []
    return list(parsed) if isinstance(parsed, list) else []


def _to_dict(rec: TaskRecord) -> dict[str, Any]:
    d = asdict(rec)
    d["started_at"] = rec.started_at.isoformat()
    d["failure_mode"] = rec.failure_mode.value
    d["actions"] = [_redact(a) for a in d["actions"]]
    return d


def append_task_record(record: TaskRecord) -> Path:
    """Append one record to the day's control-*.md file."""
    path = _path_for(record.started_at)
    existing = _existing_records(path)
    existing.append(_to_dict(record))

    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(existing, sort_keys=False, allow_unicode=True)
    text = (
        f"# /control task records -- {record.started_at.date().isoformat()}\n\n"
        "```yaml\n"
        f"{body}"
        "```\n"
    )
    path.write_text(text, encoding="utf-8")
    return path
