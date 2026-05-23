"""ToolUseContext — typed scratch object threaded through every tool call.

Mirrors claude-leak/src/Tool.ts:158-300 (`ToolUseContext`).

Design rules:
- Tools must accept `ctx: ToolUseContext` and never reach for module globals.
- `fork(agent_id=...)` creates a child context that inherits app_state by deep
  copy; mutations on the child don't leak to the parent.
- `abort_event` is shared across the agent loop and all tools so a single
  abort signal stops everything cleanly.

Note: this module is named context_scratch.py rather than context.py because
the vendored MacOS-Use code already uses yuki/agent/context/ as a package
holding prompt-context construction. Keeping them separate avoids import
collisions until we either rename one or merge them in a later plan.
"""

from __future__ import annotations

import asyncio
import copy
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolUseContext:
    session_id: str
    agent_id: str
    abort_event: asyncio.Event
    _app_state: dict[str, Any] = field(default_factory=dict)
    _read_file_cache: dict[str, str] = field(default_factory=dict)

    @classmethod
    def bare(cls) -> ToolUseContext:
        return cls(
            session_id=uuid.uuid4().hex[:12],
            agent_id="root",
            abort_event=asyncio.Event(),
        )

    def get_app_state(self, key: str, default: Any = None) -> Any:
        return self._app_state.get(key, default)

    def set_app_state(self, key: str, value: Any) -> None:
        self._app_state[key] = value

    def cache_read_file(self, path: str, content: str) -> None:
        self._read_file_cache[path] = content

    def get_cached_read(self, path: str) -> str | None:
        return self._read_file_cache.get(path)

    def fork(self, *, agent_id: str) -> ToolUseContext:
        return ToolUseContext(
            session_id=self.session_id,
            agent_id=agent_id,
            abort_event=self.abort_event,  # shared
            _app_state=copy.deepcopy(self._app_state),
            _read_file_cache=copy.deepcopy(self._read_file_cache),
        )
