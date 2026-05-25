"""AllowRules: session/project/user scoping; revoke; per-arg matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yuki.safety.allow_rules import AllowRules


@pytest.fixture
def tmp_rules_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("YUKI_ALLOW_RULES_DIR", str(tmp_path))
    return tmp_path


def test_session_rule_only_persists_in_memory(tmp_rules_dir: Path) -> None:
    r = AllowRules(session_id="s1")
    r.allow(tool_name="mail", scope="session")
    assert r.is_allowed(tool_name="mail") is True
    assert not (tmp_rules_dir / "user.json").exists()


def test_user_rule_writes_to_disk(tmp_rules_dir: Path) -> None:
    r = AllowRules(session_id="s1")
    r.allow(tool_name="calendar", scope="user")
    data = json.loads((tmp_rules_dir / "user.json").read_text())
    tool_names = [rule["tool"] for rule in data["tools"]]
    assert "calendar" in tool_names


def test_user_rule_loaded_on_init(tmp_rules_dir: Path) -> None:
    r = AllowRules(session_id="s1")
    r.allow(tool_name="reminders", scope="user")
    r2 = AllowRules(session_id="s2")
    assert r2.is_allowed(tool_name="reminders") is True


def test_revoke_user_rule(tmp_rules_dir: Path) -> None:
    r = AllowRules(session_id="s1")
    r.allow(tool_name="x", scope="user")
    r.revoke(tool_name="x", scope="user")
    assert r.is_allowed(tool_name="x") is False


def test_per_arg_scoping(tmp_rules_dir: Path) -> None:
    r = AllowRules(session_id="s1")
    r.allow(tool_name="files", scope="session", args_match={"action": "read"})
    assert (
        r.is_allowed(tool_name="files", args={"action": "read", "path": "/x"})
        is True
    )
    assert (
        r.is_allowed(tool_name="files", args={"action": "delete", "path": "/x"})
        is False
    )
