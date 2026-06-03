"""Dataset record format + validator for Yuki tool-call fine-tuning.

The fine-tune target matches how the agent ACTUALLY invokes the model (the
single-loop native tool-calling path in yuki/providers/ollama/llm.py), NOT the
deferred Phase-A2 planner. Each training record is one decision:

    given a task (and optionally a screen-state hint) + the available tools,
    emit ONE correct tool call (name + arguments incl. the `thought` preamble).

A record is a dict:

    {
      "task": "open calculator",
      "screen": "" | "<pruned AX-tree text>",   # optional context for reactive tasks
      "tool": "app_tool",                          # the correct tool name
      "args": {"thought": "...", "mode": "launch", "name": "Calculator"}
    }

`validate_record` enforces TWO layers (see module note in the plan):
  1. schema-validity  — args satisfy the tool's Pydantic required fields.
  2. functional-correctness — the call actually does something useful
     (e.g. app_tool carries a `name`, type_tool carries `text`).
This prevents training on technically-valid-but-useless calls.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, TypedDict


class Record(TypedDict):
    task: str
    screen: str
    tool: str
    args: dict[str, Any]


# Functional-correctness requirements beyond the Pydantic schema: the arg(s)
# without which a call is technically valid but does nothing. Keyed by tool.
# (done_tool's `answer` is already schema-required, so it's covered by layer 1.)
_FUNCTIONAL_ARGS: dict[str, tuple[str, ...]] = {
    "app_tool": ("name",),
    "type_tool": ("text",),
    "click_tool": ("loc",),
    "shortcut_tool": ("shortcut",),
    "shell_tool": ("command",),
    "scroll_tool": ("direction",),
    "move_tool": ("loc",),
    "read_app_note": ("bundle_id",),
}


@lru_cache(maxsize=1)
def _tool_index() -> dict[str, Any]:
    """Map tool name -> Tool object (cached; importing tools is heavyish)."""
    from yuki.agent.tools import BUILTIN_TOOLS

    return {t.name: t for t in BUILTIN_TOOLS}


def valid_tool_names() -> set[str]:
    return set(_tool_index().keys())


def validate_record(rec: dict[str, Any]) -> list[str]:
    """Return a list of problems with a record. Empty list == valid.

    Layer 1: the tool exists and its args satisfy the Pydantic schema
             (validated via the real Tool.validate_params).
    Layer 2: functional args present (the call does something useful).
    """
    problems: list[str] = []

    task = rec.get("task")
    if not isinstance(task, str) or not task.strip():
        problems.append("task: missing or empty")

    tool = rec.get("tool")
    tools = _tool_index()
    if tool not in tools:
        problems.append(f"tool: unknown {tool!r}")
        return problems  # can't validate args without a known tool

    args = rec.get("args")
    if not isinstance(args, dict):
        problems.append("args: not a dict")
        return problems

    # Layer 1: schema validity via the real tool. validate_params returns a
    # list of "field:msg" strings; empty means valid.
    schema_errors = tools[tool].validate_params(args)
    # `thought` is a preamble the registry forgives at runtime; for TRAINING
    # data we want it present, so do NOT exempt it here — a missing-thought
    # record is a bad training row (teaches the model to omit it).
    problems.extend(f"schema: {e}" for e in schema_errors)

    # Layer 2: functional correctness.
    for required in _FUNCTIONAL_ARGS.get(tool, ()):
        if required not in args or args[required] in (None, "", []):
            problems.append(f"functional: {tool} missing useful arg {required!r}")

    return problems


def is_valid(rec: dict[str, Any]) -> bool:
    return not validate_record(rec)
