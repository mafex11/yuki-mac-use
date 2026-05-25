"""music_tool: now_playing, play, play_playlist, unknown."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.music_tool import music_tool


async def test_now_playing_returns_dict() -> None:
    with patch(
        "yuki.tools.native.music_tool.osa",
        new=AsyncMock(return_value="Song | Artist | Album"),
    ):
        out = await music_tool(action="now_playing")
    assert out["title"] == "Song"
    assert out["artist"] == "Artist"


async def test_play_runs_osa() -> None:
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.music_tool.osa", new=fake):
        out = await music_tool(action="play")
    assert out == {"ok": True}


async def test_play_playlist_passes_name() -> None:
    fake = AsyncMock(return_value="")
    with patch("yuki.tools.native.music_tool.osa", new=fake):
        out = await music_tool(action="play_playlist", playlist="Deep Work")
    assert out == {"ok": True}
    fake.assert_awaited()


async def test_unknown_raises() -> None:
    with pytest.raises(ValueError):
        await music_tool(action="zzz")
