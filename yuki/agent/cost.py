"""Per-session cost tracker — persists token usage to disk for BYO-key users.

Mirrors the pattern in claude-leak/src/cost-tracker.ts:143. Each agent
session writes a JSON snapshot to
    ~/Library/Application Support/Yuki/sessions/<session_id>.cost.json

Override the directory via YUKI_COST_DIR for tests.

This is plumbing — the agent loop calls record() after each LLM response.
The cost router (Plan I) reads totals to surface in the UI.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path


def _root() -> Path:
    override = os.environ.get("YUKI_COST_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Yuki" / "sessions"


class CostTracker:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._totals: dict[str, int] = defaultdict(int)
        self._by_model: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int),
        )
        self._load()

    def _path(self) -> Path:
        return _root() / f"{self._session_id}.cost.json"

    def _load(self) -> None:
        path = self._path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for k, v in (data.get("totals") or {}).items():
            self._totals[k] = int(v)
        for model, counts in (data.get("by_model") or {}).items():
            for k, v in counts.items():
                self._by_model[model][k] = int(v)

    def record(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_creation_tokens: int,
        model: str,
    ) -> None:
        for k, v in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
        }.items():
            self._totals[k] += v
            self._by_model[model][k] += v
        self._save()

    def totals(self) -> dict[str, int]:
        return dict(self._totals)

    def _save(self) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "session_id": self._session_id,
                    "totals": dict(self._totals),
                    "by_model": {m: dict(c) for m, c in self._by_model.items()},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
