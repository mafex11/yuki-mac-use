"""files_tool: find (mdfind), read with safety, delete refusal."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuki.tools.native.files_tool import files_tool


async def test_find_uses_mdfind(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(
        return_value=(b"/Users/me/a.txt\n/Users/me/b.txt\n", b"")
    )
    fake_proc.returncode = 0

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    out = await files_tool(action="find", query="kMDItemKind == 'Plain Text'")
    assert out == ["/Users/me/a.txt", "/Users/me/b.txt"]


async def test_read_returns_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    monkeypatch.setattr("yuki.tools.native.files_tool._allowed", lambda path: True)
    out = await files_tool(action="read", path=str(p))
    assert out == "hello"


async def test_delete_refuses_outside_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("yuki.tools.native.files_tool._allowed", lambda path: False)
    out = await files_tool(action="delete", path="/etc/passwd")
    assert "refused" in out.get("error", "").lower()


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await files_tool(action="zzz")
