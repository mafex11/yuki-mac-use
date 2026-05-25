"""Tool decorator + danger classification + global registry."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, get_type_hints


class DangerLevel(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE = "reversible"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class ToolSpec:
    """Tool descriptor — required: name, danger, description, parameters, fn.

    Optional: experimental flag, max_result_size_chars (oversize → spillover),
    validate_input (extra checks beyond JSON schema), check_permissions
    (returns 'allow' | 'ask' | 'deny'), prompt (per-tool system fragment).
    """

    name: str
    danger: DangerLevel
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Awaitable[Any]]
    experimental: bool = False
    max_result_size_chars: int = 50_000
    validate_input: Callable[[dict[str, Any]], None] | None = None
    check_permissions: Callable[[dict[str, Any], Any], str] | None = None
    prompt: str = ""

    @property
    def is_read_only(self) -> bool:
        return self.danger == DangerLevel.READ_ONLY

    @property
    def is_destructive(self) -> bool:
        return self.danger == DangerLevel.DESTRUCTIVE


REGISTRY: dict[str, ToolSpec] = {}


def _build_parameters(fn: Callable[..., Any]) -> dict[str, Any]:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        py_type = hints.get(name, str)
        properties[name] = {"type": _TYPE_MAP.get(py_type, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def tool(
    *,
    name: str,
    danger: DangerLevel,
    experimental: bool = False,
    max_result_size_chars: int = 50_000,
    validate_input: Callable[[dict[str, Any]], None] | None = None,
    check_permissions: Callable[[dict[str, Any], Any], str] | None = None,
    prompt: str = "",
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        REGISTRY[name] = ToolSpec(
            name=name,
            danger=danger,
            description=(fn.__doc__ or "").strip(),
            parameters=_build_parameters(fn),
            fn=fn,
            experimental=experimental,
            max_result_size_chars=max_result_size_chars,
            validate_input=validate_input,
            check_permissions=check_permissions,
            prompt=prompt,
        )
        return fn

    return decorate


def get(name: str) -> ToolSpec:
    return REGISTRY[name]


def list_specs(*, include_experimental: bool = False) -> list[ToolSpec]:
    return [
        s for s in REGISTRY.values() if include_experimental or not s.experimental
    ]
