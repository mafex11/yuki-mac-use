"""Slash pipeline: pass-through, local, prompt, unknown."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from yuki.runtime.commands.base import CommandResult, LocalCommand, PromptCommand
from yuki.runtime.commands.pipeline import process_user_input
from yuki.runtime.commands.registry import REGISTRY, register


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    saved = dict(REGISTRY)
    REGISTRY.clear()
    yield
    REGISTRY.clear()
    REGISTRY.update(saved)


def test_unmatched_passes_through() -> None:
    result = process_user_input("hello world")
    assert result.kind == "agent"
    assert result.text == "hello world"


def test_local_command_short_circuits() -> None:
    register(
        LocalCommand(
            name="hi",
            run=lambda args: CommandResult.local_text("hi back"),
        )
    )
    result = process_user_input("/hi")
    assert result.kind == "local_text"
    assert result.text == "hi back"


def test_prompt_command_emits_user_message() -> None:
    register(
        PromptCommand(
            name="explain",
            prompt_template="Explain this in detail: {args}",
        )
    )
    result = process_user_input("/explain quicksort")
    assert result.kind == "agent"
    assert "Explain this" in result.text
    assert "quicksort" in result.text


def test_unknown_slash_falls_through_as_agent_message() -> None:
    result = process_user_input("/nope")
    assert result.kind == "agent"
    assert result.text == "/nope"
