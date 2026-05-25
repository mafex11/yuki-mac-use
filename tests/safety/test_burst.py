"""BurstMode: initial inactive, engage, re-engage, disengage."""

from __future__ import annotations

import asyncio

from yuki.safety.burst import BurstMode


async def test_initial_inactive() -> None:
    b = BurstMode()
    assert b.is_active() is False


async def test_engage_active_for_duration() -> None:
    b = BurstMode()
    b.engage(duration=0.05)
    assert b.is_active() is True
    await asyncio.sleep(0.1)
    assert b.is_active() is False


async def test_re_engage_extends() -> None:
    b = BurstMode()
    b.engage(duration=0.05)
    await asyncio.sleep(0.03)
    b.engage(duration=0.1)
    await asyncio.sleep(0.05)
    assert b.is_active() is True


async def test_disengage_immediate() -> None:
    b = BurstMode()
    b.engage(duration=10)
    b.disengage()
    assert b.is_active() is False
