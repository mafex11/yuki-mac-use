"""Git collector — walks roots for .git dirs, summarizes log."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from yuki.scan.collectors.git import GitCollector


def _make_repo(root: Path, name: str, commits: int) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    for i in range(commits):
        (repo / f"f{i}").write_text(str(i))
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"commit {i}"], cwd=repo, check=True)
    return repo


@pytest.mark.asyncio
async def test_git_collector_walks_repos(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    _make_repo(tmp_path, "alpha", 3)
    _make_repo(tmp_path, "nested/beta", 1)
    rows = await GitCollector(roots=[tmp_path]).collect()
    names = {r["name"] for r in rows}
    assert names == {"alpha", "beta"}
    alpha = next(r for r in rows if r["name"] == "alpha")
    assert alpha["commit_count"] >= 3
    assert any("commit 0" in s for s in alpha["recent_subjects"])


@pytest.mark.asyncio
async def test_git_collector_skips_non_repo(tmp_path: Path) -> None:
    (tmp_path / "not_a_repo").mkdir()
    rows = await GitCollector(roots=[tmp_path]).collect()
    assert rows == []


@pytest.mark.asyncio
async def test_git_collector_missing_root(tmp_path: Path) -> None:
    rows = await GitCollector(roots=[tmp_path / "nope"]).collect()
    assert rows == []
