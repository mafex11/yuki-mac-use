"""TimeTicker: fires callback periodically; swallows callback errors."""

from __future__ import annotations

import asyncio
from datetime import datetime

from yuki.triggers.ticker import TimeTicker


async def test_ticker_calls_callback() -> None:
    calls: list[datetime] = []

    async def cb(now: datetime) -> None:
        calls.append(now)

    ticker = TimeTicker(callback=cb, interval=0.05)
    await ticker.start()
    await asyncio.sleep(0.2)
    await ticker.stop()
    assert len(calls) >= 2


async def test_ticker_swallows_callback_errors() -> None:
    calls = [0]

    async def cb(now: datetime) -> None:
        calls[0] += 1
        raise RuntimeError("boom")

    ticker = TimeTicker(callback=cb, interval=0.05)
    await ticker.start()
    await asyncio.sleep(0.2)
    await ticker.stop()
    assert calls[0] >= 2
