"""System collector — uses sw_vers, defaults, hostname."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from yuki.scan.collectors.system import SystemCollector


@pytest.mark.asyncio
async def test_collects_system_facts() -> None:
    fake_outputs = {
        ("sw_vers", "-productVersion"): "14.4.1\n",
        ("sw_vers", "-buildVersion"): "23E224\n",
        ("hostname",): "my-mac.local\n",
        ("defaults", "read", "-g", "AppleLocale"): "en_US\n",
    }

    async def fake_run(*args: str) -> str:
        return fake_outputs.get(args, "").strip()

    with patch("yuki.scan.collectors.system._run", side_effect=fake_run):
        rows = await SystemCollector().collect()

    assert len(rows) == 1
    assert rows[0]["macos_version"] == "14.4.1"
    assert rows[0]["locale"] == "en_US"
    assert rows[0]["hostname"] == "my-mac.local"


@pytest.mark.asyncio
async def test_handles_missing_outputs() -> None:
    async def fake_run(*args: str) -> str:
        return ""

    with patch("yuki.scan.collectors.system._run", side_effect=fake_run):
        rows = await SystemCollector().collect()
    assert len(rows) == 1
    assert rows[0]["macos_version"] == ""
