"""Shell history collector — zsh extended-history + bash fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from yuki.scan.collectors.shell import ShellCollector


@pytest.mark.asyncio
async def test_zsh_extended_history(tmp_home: Path) -> None:
    hist = tmp_home / ".zsh_history"
    hist.write_text(
        ": 1700000000:0;git status\n"
        ": 1700000001:0;git status\n"
        ": 1700000002:0;npm test\n"
        ": 1700000003:0;cd ~/code\n",
        encoding="utf-8",
    )
    rows = await ShellCollector().collect()
    by_cmd = {r["command"]: r for r in rows}
    assert by_cmd["git"]["count"] == 2
    assert by_cmd["npm"]["count"] == 1


@pytest.mark.asyncio
async def test_bash_history_fallback(tmp_home: Path) -> None:
    hist = tmp_home / ".bash_history"
    hist.write_text("ls\nls\npwd\n", encoding="utf-8")
    rows = await ShellCollector().collect()
    cmds = {r["command"]: r["count"] for r in rows}
    assert cmds == {"ls": 2, "pwd": 1}


@pytest.mark.asyncio
async def test_no_history_returns_empty(tmp_home: Path) -> None:
    rows = await ShellCollector().collect()
    assert rows == []
