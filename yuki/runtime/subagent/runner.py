"""run_subagent — async generator that executes a subagent loop and streams events.

Mirrors claude-leak/src/tools/AgentTool/runAgent.ts. Records sidechain transcripts
to ~/Library/Application Support/Yuki/sidechains/ and yields {type: ..., ...} dicts.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yuki.runtime.subagent.definition import AgentDefinition


def _sidechain_dir() -> Path:
    override = os.environ.get("YUKI_SIDECHAIN_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "Yuki" / "sidechains"


def _record(agent_id: str, event: dict[str, Any]) -> None:
    root = _sidechain_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"agent-{agent_id}.jsonl"
    stamped = {**event, "ts": datetime.now(UTC).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(stamped, default=str) + "\n")


async def run_subagent(
    *,
    definition: AgentDefinition,
    prompt: str,
    llm: Any,
    parent_ctx: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run a subagent loop. Yields {type: start|assistant|result|error} dicts."""
    agent_id = uuid.uuid4().hex[:12]

    _record(
        agent_id,
        {"type": "start", "definition": definition.name, "prompt": prompt},
    )
    yield {"type": "start", "agent_id": agent_id, "definition": definition.name}

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": definition.system_prompt},
        {"role": "user", "content": prompt},
    ]

    response = await llm.invoke(messages)
    blocks = response.content
    yield {"type": "assistant", "agent_id": agent_id, "content": blocks}
    _record(agent_id, {"type": "assistant", "content": blocks})

    final_text = ""
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            final_text = b.get("text", "")
            break

    yield {"type": "result", "agent_id": agent_id, "content": final_text}
    _record(agent_id, {"type": "result", "content": final_text})
