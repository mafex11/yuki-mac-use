"""Files collector — mdfind output parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from yuki.scan.collectors.files import FilesCollector


@pytest.mark.asyncio
async def test_files_collector_groups_by_dir() -> None:
    fake_stdout = (
        "/Users/me/code/yuki/main.py\n"
        "/Users/me/code/yuki/test.py\n"
        "/Users/me/code/yuki/README.md\n"
        "/Users/me/Documents/notes.txt\n"
    )

    async def fake_run(*args: str) -> str:
        return fake_stdout

    with patch("yuki.scan.collectors.files._run", side_effect=fake_run):
        rows = await FilesCollector().collect()

    by_dir = {r["directory"]: r["count"] for r in rows}
    assert by_dir["/Users/me/code/yuki"] == 3
    assert by_dir["/Users/me/Documents"] == 1


@pytest.mark.asyncio
async def test_files_collector_empty_output() -> None:
    async def fake_run(*args: str) -> str:
        return ""

    with patch("yuki.scan.collectors.files._run", side_effect=fake_run):
        rows = await FilesCollector().collect()
    assert rows == []
