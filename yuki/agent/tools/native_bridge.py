"""Bridge yuki/tools/native/* ToolSpecs into desktop-agent Tools.

The native registry holds high-level AppleScript tools (spotify, music,
browser, calendar, ...) that act in one deterministic call where GUI
navigation would take many fragile steps. Until now they were only exposed
over GET /tools — the desktop agent never saw them. This module wraps each
ToolSpec into the agent's Tool protocol so the LLM can call them directly.

Wrapping rules:
- Agent-facing name is "<spec.name>_tool" to match the existing convention.
- Params get a pydantic model derived from the spec's JSON schema, based on
  SharedBaseModel so the evaluate/plan/thought preamble stays uniform.
- The wrapper drops the injected `desktop` kwarg (native fns don't take it)
  and serializes non-string results to JSON for the ToolMessage.
- Experimental specs are skipped, mirroring registry.list_specs().
"""

from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import Field, create_model

from yuki.agent.tools.views import SharedBaseModel
from yuki.tools import Tool
from yuki.tools.native.registry import ToolSpec, list_specs
from yuki.tools.spillover import maybe_spill

_JSON_TO_PY: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _params_model(spec: ToolSpec):
    """Build a SharedBaseModel subclass from the spec's JSON-schema params."""
    props: dict[str, Any] = spec.parameters.get("properties", {})
    required = set(spec.parameters.get("required", []))
    fields: dict[str, Any] = {}
    for pname, pschema in props.items():
        py = _JSON_TO_PY.get(pschema.get("type", "string"), str)
        if pname in required:
            fields[pname] = (py, Field(...))
        else:
            fields[pname] = (Optional[py], Field(default=None))
    return create_model(f"{spec.name.title()}Native", __base__=SharedBaseModel, **fields)


def _make_wrapper(spec: ToolSpec):
    async def wrapper(**kwargs: Any) -> str:
        params = {
            k: v
            for k, v in kwargs.items()
            if k in spec.parameters.get("properties", {}) and v is not None
        }
        result = await spec.fn(**params)
        result = maybe_spill(
            result, max_chars=spec.max_result_size_chars, tool_name=spec.name
        )
        if isinstance(result, str):
            return result
        return json.dumps(result, default=str)

    wrapper.__name__ = f"{spec.name}_tool"
    wrapper.__doc__ = spec.description
    return wrapper


def build_native_agent_tools(exclude: set[str] | None = None) -> list[Tool]:
    """Wrap every non-experimental native ToolSpec as an agent Tool.

    `exclude` filters by native spec name (e.g. {"files"}) for callers that
    want to withhold specific capabilities.
    """
    tools: list[Tool] = []
    for spec in list_specs():
        if exclude and spec.name in exclude:
            continue
        t = Tool(
            f"{spec.name}_tool",
            description=spec.description,
            model=_params_model(spec),
        )
        t(_make_wrapper(spec))
        tools.append(t)
    return tools
