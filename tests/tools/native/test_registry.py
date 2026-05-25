"""Tool registry: decorator behavior, schema generation, optional fields."""

from __future__ import annotations

from typing import Any

from yuki.tools.native.registry import REGISTRY, DangerLevel, ToolSpec, get, tool


def test_tool_decorator_registers() -> None:
    @tool(name="add", danger=DangerLevel.READ_ONLY)
    async def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    assert "add" in REGISTRY
    assert isinstance(get("add"), ToolSpec)
    assert get("add").danger == DangerLevel.READ_ONLY


def test_tool_describes_args_from_hints() -> None:
    @tool(name="hello", danger=DangerLevel.READ_ONLY)
    async def hello(name: str, exclaim: bool = False) -> str:
        """Say hello."""
        return f"hello {name}"

    spec = get("hello")
    assert spec.parameters["properties"]["name"]["type"] == "string"
    assert spec.parameters["properties"]["exclaim"]["type"] == "boolean"
    assert spec.parameters["required"] == ["name"]


def test_duplicate_name_overwrites() -> None:
    @tool(name="x", danger=DangerLevel.READ_ONLY)
    async def x() -> str:
        """v1"""
        return "v1"

    @tool(name="x", danger=DangerLevel.READ_ONLY)
    async def x2() -> str:
        """v2"""
        return "v2"

    assert get("x").description == "v2"


def test_spec_carries_optional_fields() -> None:
    def _v(args: dict[str, Any]) -> None:
        if not args.get("a"):
            raise ValueError("a required")

    @tool(
        name="rich",
        danger=DangerLevel.REVERSIBLE,
        max_result_size_chars=1234,
        validate_input=_v,
        prompt="Use this only for X.",
    )
    async def rich(a: str) -> str:
        """."""
        return a

    spec = get("rich")
    assert spec.max_result_size_chars == 1234
    assert spec.validate_input is _v
    assert spec.prompt == "Use this only for X."
    assert spec.is_read_only is False
    assert spec.is_destructive is False


async def test_invoke_runs_underlying() -> None:
    @tool(name="add", danger=DangerLevel.READ_ONLY)
    async def add(a: int, b: int) -> int:
        """."""
        return a + b

    assert await get("add").fn(2, 3) == 5
