"""Compactor — last-7-days of episodes → vault diff via the configured LLM."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from yuki.episodist.diff import VaultDiff
from yuki.memory import paths
from yuki.memory.vault import Vault
from yuki.messages import HumanMessage

log = logging.getLogger(__name__)
_MAX_TOKENS = 4000
_DAYS = 7

_PROMPT = """You are inspecting a user's recent computer activity to identify
recurring patterns worth capturing as routines or important people.

DO NOT propose `type: app` entries -- application guidance is managed by
a separate daily process.

Output ONLY a JSON object with this shape:
{
  "entries": [
    {
      "action": "create",
      "confidence": 0.0..1.0,
      "note": { ...frontmatter for one note, must include id, type, name and
                fields valid for that type per the schema... }
    }, ...
  ]
}

Be conservative. Do not invent details. Only output entries you have
strong evidence for from the episodes below."""


def _client() -> Any:
    """Build an LLM via the provider factory (same as /chat)."""
    from yuki.providers.factory import make_llm

    return make_llm()


@dataclass
class CompactResult:
    applied: int
    diff: VaultDiff | None


def _gather(today: date) -> list[Path]:
    eps_dir = paths.vault_dir() / "60-Episodes"
    if not eps_dir.exists():
        return []
    out: list[Path] = []
    for i in range(_DAYS):
        d = today - timedelta(days=i)
        f = eps_dir / f"{d.isoformat()}.md"
        if f.exists():
            out.append(f)
    return out


def compact_last_week(*, today: date) -> CompactResult:
    files = _gather(today)
    if not files:
        return CompactResult(applied=0, diff=None)
    body = "\n\n---\n\n".join(p.read_text() for p in files)
    try:
        llm = _client()
        event = asyncio.run(
            llm.ainvoke(
                messages=[HumanMessage(content=f"{_PROMPT}\n\n{body}")],
                tools=[],
            )
        )
        text = (event.content or "").strip() if event else ""
        diff = VaultDiff.from_json(text)
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        log.warning("compactor parse failed: %s", e)
        return CompactResult(applied=0, diff=None)
    except Exception as e:
        log.warning("compactor LLM call failed: %s", e)
        return CompactResult(applied=0, diff=None)
    applied = diff.apply(vault=Vault())
    return CompactResult(applied=applied, diff=diff)
