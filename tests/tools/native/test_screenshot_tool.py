"""screenshot_tool: writes png at scratch path; unknown action."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from yuki.tools.native.screenshot_tool import screenshot_tool


async def test_take_writes_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_path = tmp_path / "shot.png"
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"", b""))
    fake_proc.returncode = 0

    async def fake_create(*args: Any, **kwargs: Any) -> Any:
        out_path.write_bytes(b"PNGDATA")
        return fake_proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create)
    monkeypatch.setattr(
        "yuki.tools.native.screenshot_tool._scratch_path", lambda: out_path
    )
    out = await screenshot_tool(action="take")
    assert out["path"] == str(out_path)
    assert out_path.exists()


async def test_unknown_action_raises() -> None:
    with pytest.raises(ValueError):
        await screenshot_tool(action="nope")
