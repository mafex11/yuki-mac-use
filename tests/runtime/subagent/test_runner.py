"""run_subagent: yields events, records sidechain transcript."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from yuki.runtime.subagent.definition import AgentDefinition
from yuki.runtime.subagent.runner import run_subagent


async def test_run_subagent_yields_messages(fake_llm: Any) -> None:
    fake_llm.queue([{"type": "text", "text": "subagent done"}])

    definition = AgentDefinition(
        name="explore", system_prompt="You are read-only."
    )

    out: list[dict[str, Any]] = []
    async for msg in run_subagent(
        definition=definition, prompt="what's in src/?", llm=fake_llm
    ):
        out.append(msg)
    assert any(m.get("type") == "assistant" for m in out)
    assert any(m.get("type") == "result" for m in out)


async def test_run_subagent_records_sidechain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_llm: Any
) -> None:
    monkeypatch.setenv("YUKI_SIDECHAIN_DIR", str(tmp_path))
    fake_llm.queue([{"type": "text", "text": "ok"}])
    definition = AgentDefinition(name="x", system_prompt="x")

    async for _ in run_subagent(
        definition=definition, prompt="hi", llm=fake_llm
    ):
        pass

    files = list(tmp_path.glob("agent-*.jsonl"))
    assert len(files) == 1
    text = files[0].read_text()
    assert "start" in text
