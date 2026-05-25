"""Git collector — walks configured roots for repos, summarizes recent commits."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


async def _run_in(cwd: Path, *args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8", errors="replace")


class GitCollector:
    name = "git"

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path.home() / "code"]
        self._roots = roots

    async def collect(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for root in self._roots:
            if not root.exists():
                continue
            for path in self._find_repos(root):
                row = await self._summarize(path)
                if row is not None:
                    rows.append(row)
        return rows

    def _find_repos(self, root: Path) -> list[Path]:
        repos: list[Path] = []
        for path in root.rglob(".git"):
            if path.is_dir():
                repos.append(path.parent)
        return repos

    async def _summarize(self, repo: Path) -> dict[str, Any] | None:
        log = await _run_in(repo, "git", "log", "--pretty=format:%aI%x09%s", "-n", "50")
        if not log.strip():
            return None
        lines = [line.split("\t", 1) for line in log.splitlines() if "\t" in line]
        if not lines:
            return None
        last_iso = lines[0][0]
        subjects = [s for _, s in lines[:20]]
        return {
            "name": repo.name,
            "path": str(repo),
            "last_commit": last_iso,
            "commit_count": len(lines),
            "recent_subjects": subjects,
        }
