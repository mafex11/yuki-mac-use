"""Validator for Yuki tool-call training records (two-layer checks)."""

from __future__ import annotations

from training.schema import is_valid, valid_tool_names, validate_record


def _app_open() -> dict:
    return {
        "task": "open calculator",
        "screen": "",
        "tool": "app_tool",
        "args": {"thought": "Launch Calculator.", "mode": "launch", "name": "Calculator"},
    }


def test_valid_app_record() -> None:
    assert validate_record(_app_open()) == []
    assert is_valid(_app_open())


def test_unknown_tool_rejected() -> None:
    rec = _app_open()
    rec["tool"] = "open_app"  # not a real Yuki tool
    problems = validate_record(rec)
    assert any("unknown" in p for p in problems)


def test_missing_thought_is_a_bad_training_row() -> None:
    # The registry forgives a missing `thought` at runtime, but a training row
    # without it teaches the model to omit it — so it must be rejected here.
    rec = _app_open()
    del rec["args"]["thought"]
    problems = validate_record(rec)
    assert any("thought" in p for p in problems)


def test_app_tool_without_name_is_functionally_invalid() -> None:
    # Schema-valid (only `thought` is schema-required) but useless: no app named.
    rec = {
        "task": "open something",
        "screen": "",
        "tool": "app_tool",
        "args": {"thought": "Open it."},
    }
    problems = validate_record(rec)
    assert any("functional" in p and "name" in p for p in problems)


def test_done_tool_requires_answer() -> None:
    rec = {
        "task": "say hi",
        "screen": "",
        "tool": "done_tool",
        "args": {"thought": "Greet."},  # missing answer (schema-required)
    }
    assert not is_valid(rec)


def test_done_tool_valid_with_answer() -> None:
    rec = {
        "task": "say hi",
        "screen": "",
        "tool": "done_tool",
        "args": {"thought": "Greet.", "answer": "Hello!"},
    }
    assert is_valid(rec)


def test_empty_task_rejected() -> None:
    rec = _app_open()
    rec["task"] = "  "
    assert not is_valid(rec)


def test_valid_tool_names_matches_registry() -> None:
    names = valid_tool_names()
    assert "app_tool" in names and "done_tool" in names
    # Registry size floats as native tools are added; pin only the essentials.
    assert {"click_tool", "type_tool", "shell_tool", "shortcut_tool"} <= names
