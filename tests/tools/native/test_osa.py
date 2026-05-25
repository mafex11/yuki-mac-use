"""osa: stdout, error, timeout."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from yuki.tools.native.osa import OsaError, osa


async def test_osa_returns_stdout() -> None:
    fake = AsyncMock(return_value=(0, "hello\n"))
    with patch("yuki.tools.native.osa._spawn", new=fake):
        out = await osa("-e", 'return "hello"')
    assert out == "hello"


async def test_osa_raises_on_nonzero() -> None:
    fake = AsyncMock(return_value=(1, "boom"))
    with patch("yuki.tools.native.osa._spawn", new=fake), pytest.raises(OsaError):
        await osa("-e", "broken")


async def test_osa_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hang(*args: Any, **kwargs: Any) -> tuple[int, str]:
        await asyncio.sleep(2)
        return (0, "")

    monkeypatch.setattr("yuki.tools.native.osa._spawn", hang)
    with pytest.raises(OsaError):
        await osa("-e", "x", timeout=0.05)
