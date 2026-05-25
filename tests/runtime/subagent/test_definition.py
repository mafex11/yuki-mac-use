"""AgentDefinition: minimal/explicit/invalid name."""

from __future__ import annotations

import pytest

from yuki.runtime.subagent.definition import AgentDefinition


def test_minimal_definition() -> None:
    d = AgentDefinition(
        name="explore",
        system_prompt="You are a code-search subagent.",
    )
    assert d.name == "explore"
    assert d.allowed_tools is None
    assert d.is_read_only is True


def test_explicit_allowed_tools() -> None:
    d = AgentDefinition(
        name="builder",
        system_prompt="You write code.",
        allowed_tools=["files", "shell"],
    )
    assert d.allowed_tools == ["files", "shell"]
    assert d.is_read_only is False


def test_invalid_name_rejected() -> None:
    with pytest.raises(ValueError):
        AgentDefinition(name="has spaces", system_prompt="x")
