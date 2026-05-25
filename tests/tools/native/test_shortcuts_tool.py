"""shortcuts_tool: list, run success, run failure."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuki.tools.native.shortcuts_tool import shortcuts_tool


async def test_list_parses_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"Foo\nBar\n", b""))
    fake_proc.returncode = 0

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="list")
    assert out == ["Foo", "Bar"]


async def test_run_returns_output(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"42\n", b""))
    fake_proc.returncode = 0

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="run", name="MyShortcut", input_text="hi")
    assert out["output"] == "42"


async def test_run_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b"not found"))
    fake_proc.returncode = 1

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await shortcuts_tool(action="run", name="missing")
    assert "error" in out
