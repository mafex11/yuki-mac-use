"""Native-tool tests: clean registry between tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from yuki.tools.native import registry as reg


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    saved = dict(reg.REGISTRY)
    reg.REGISTRY.clear()
    yield
    reg.REGISTRY.clear()
    reg.REGISTRY.update(saved)
