"""clipboard_tool: round-trip and history cap."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest

from yuki.tools.native import clipboard_tool as cb_mod
from yuki.tools.native.clipboard_tool import clipboard_tool


@pytest.fixture(autouse=True)
def reset_history() -> Iterator[None]:
    cb_mod._HISTORY.clear()
    yield
    cb_mod._HISTORY.clear()


async def test_write_then_read_round_trip() -> None:
    captured = {"text": ""}

    def fake_write(t: str) -> None:
        captured["text"] = t

    def fake_read() -> str:
        return captured["text"]

    with (
        patch("yuki.tools.native.clipboard_tool._pb_write", new=fake_write),
        patch("yuki.tools.native.clipboard_tool._pb_read", new=fake_read),
    ):
        await clipboard_tool(action="write", text="hello")
        out = await clipboard_tool(action="read")
    assert out == "hello"


async def test_history_keeps_last_20() -> None:
    with (
        patch("yuki.tools.native.clipboard_tool._pb_write", new=lambda t: None),
        patch("yuki.tools.native.clipboard_tool._pb_read", new=lambda: ""),
    ):
        for i in range(25):
            await clipboard_tool(action="write", text=f"v{i}")
        out = await clipboard_tool(action="history")
    assert len(out) == 20
    assert out[0] == "v24"
