"""Collector protocol + run wrapper that swallows errors and writes JSON cache."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from yuki.scan import paths

log = logging.getLogger(__name__)


class Collector(Protocol):
    name: str

    async def collect(self) -> list[dict[str, Any]]: ...


async def run_collector(collector: Collector, timeout: float = 60.0) -> list[dict[str, Any]]:
    """Run a collector with timeout + error swallowing. Always writes raw cache."""
    rows: list[dict[str, Any]] = []
    try:
        rows = await asyncio.wait_for(collector.collect(), timeout=timeout)
    except TimeoutError:
        log.warning("collector %s timed out after %.1fs", collector.name, timeout)
    except Exception as e:
        log.warning("collector %s failed: %s", collector.name, e)

    out = paths.raw_path(collector.name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, default=str), encoding="utf-8")
    return rows
