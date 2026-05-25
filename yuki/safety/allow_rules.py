"""Three-scope allow-rules: session (in-memory) / project (per-cwd) / user (global).

Mirrors Claude Code's allow-rules system. The Gatekeeper consults this BEFORE
asking the Confirmer; if any rule matches, the action auto-approves.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

Scope = Literal["session", "project", "user"]


def _user_path() -> Path:
    override = os.environ.get("YUKI_ALLOW_RULES_DIR")
    if override:
        return Path(override) / "user.json"
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "Yuki"
        / "allow-rules"
        / "user.json"
    )


def _project_path() -> Path:
    override = os.environ.get("YUKI_ALLOW_RULES_DIR")
    cwd = Path.cwd().resolve()
    safe = str(cwd).replace("/", "_")
    if override:
        return Path(override) / f"project-{safe}.json"
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "Yuki"
        / "allow-rules"
        / f"project-{safe}.json"
    )


def _matches(args_match: dict[str, Any] | None, args: dict[str, Any] | None) -> bool:
    if not args_match:
        return True
    if not args:
        return False
    return all(args.get(k) == v for k, v in args_match.items())


class AllowRules:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._session: list[dict[str, Any]] = []
        self._user: list[dict[str, Any]] = self._load(_user_path())
        self._project: list[dict[str, Any]] = self._load(_project_path())

    def _load(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        return list(data.get("tools", []))

    def _save(self, path: Path, rules: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tools": rules}, indent=2), encoding="utf-8")

    def allow(
        self,
        *,
        tool_name: str,
        scope: Scope,
        args_match: dict[str, Any] | None = None,
    ) -> None:
        rule: dict[str, Any] = {"tool": tool_name, "args_match": args_match}
        if scope == "session":
            self._session.append(rule)
        elif scope == "user":
            self._user.append(rule)
            self._save(_user_path(), self._user)
        elif scope == "project":
            self._project.append(rule)
            self._save(_project_path(), self._project)

    def revoke(
        self,
        *,
        tool_name: str,
        scope: Scope,
        args_match: dict[str, Any] | None = None,
    ) -> None:
        target: dict[str, Any] = {"tool": tool_name, "args_match": args_match}
        if scope == "session":
            self._session = [r for r in self._session if r != target]
        elif scope == "user":
            self._user = [r for r in self._user if r != target]
            self._save(_user_path(), self._user)
        elif scope == "project":
            self._project = [r for r in self._project if r != target]
            self._save(_project_path(), self._project)

    def is_allowed(
        self, *, tool_name: str, args: dict[str, Any] | None = None
    ) -> bool:
        for rules in (self._session, self._project, self._user):
            for rule in rules:
                if rule["tool"] != tool_name:
                    continue
                if _matches(rule.get("args_match"), args):
                    return True
        return False
