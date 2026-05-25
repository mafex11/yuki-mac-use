"""Collector base — timeout, error swallowing, JSON cache write."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from yuki.scan.collectors.base import Collector, run_collector


class _OkCollector:
    name = "ok"

    async def collect(self) -> list[dict[str, Any]]:
        return [{"x": 1}, {"x": 2}]


class _BoomCollector:
    name = "boom"

    async def collect(self) -> list[dict[str, Any]]:
        raise RuntimeError("kaboom")


class _SlowCollector:
    name = "slow"

    async def collect(self) -> list[dict[str, Any]]:
        await asyncio.sleep(2.0)
        return [{"never": True}]


@pytest.mark.asyncio
async def test_run_collector_writes_json(tmp_scan_cache: Path) -> None:
    rows = await run_collector(_OkCollector(), timeout=5.0)
    assert rows == [{"x": 1}, {"x": 2}]
    out = tmp_scan_cache / "raw" / "ok.json"
    assert json.loads(out.read_text()) == [{"x": 1}, {"x": 2}]


@pytest.mark.asyncio
async def test_run_collector_swallows_errors(tmp_scan_cache: Path) -> None:
    rows = await run_collector(_BoomCollector(), timeout=5.0)
    assert rows == []
    out = tmp_scan_cache / "raw" / "boom.json"
    assert json.loads(out.read_text()) == []


@pytest.mark.asyncio
async def test_run_collector_timeout(tmp_scan_cache: Path) -> None:
    rows = await run_collector(_SlowCollector(), timeout=0.05)
    assert rows == []


def test_collector_protocol_static() -> None:
    """Verify the Protocol type-checks for compliant classes."""
    c: Collector = _OkCollector()
    assert c.name == "ok"
