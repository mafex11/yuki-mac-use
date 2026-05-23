"""Git-tracking the vault — every write becomes a commit.

Borrowed from Letta MemFS: a markdown vault on disk + git history gives free
undo, free audit, and free remote sync (the user can `git remote add origin
git@github.com:them/yuki-vault.git` whenever they want).

Disable by setting YUKI_VAULT_GIT=0 (useful in tests that don't care about git).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path


def _enabled() -> bool:
    return os.environ.get("YUKI_VAULT_GIT", "1") != "0"


class VaultGit:
    def __init__(self, root: Path) -> None:
        self._root = root

    def init_if_needed(self) -> None:
        if not _enabled():
            return
        if (self._root / ".git").is_dir():
            return
        self._root.mkdir(parents=True, exist_ok=True)
        self._run("git", "init", "-q", "-b", "main")
        gi = self._root / ".gitignore"
        if not gi.exists():
            gi.write_text(".scan_complete\n", encoding="utf-8")
        self._configure_identity()
        self._run("git", "add", ".gitignore")
        self._run("git", "commit", "-q", "-m", "feat(vault): initialize")

    def commit_path(self, path: Path, *, summary: str) -> None:
        if not _enabled():
            return
        if not (self._root / ".git").is_dir():
            self.init_if_needed()
        self._run("git", "add", str(path.relative_to(self._root)))
        self._run("git", "commit", "-q", "-m", summary, check=False)

    def _configure_identity(self) -> None:
        self._run("git", "config", "user.email", "vault@yuki.local")
        self._run("git", "config", "user.name", "Yuki Vault")

    def _run(self, *args: str, check: bool = True) -> None:
        # No git on PATH or command failed — degrade silently.
        with contextlib.suppress(FileNotFoundError, subprocess.CalledProcessError):
            subprocess.run(
                args,
                cwd=str(self._root),
                check=check,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
