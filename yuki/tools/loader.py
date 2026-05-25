"""Hot-load user-defined @tool functions from ~/.yuki/tools/."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path

from yuki.tools.native.registry import REGISTRY

log = logging.getLogger(__name__)


def _user_tools_dir() -> Path:
    override = os.environ.get("YUKI_USER_TOOLS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".yuki" / "tools"


def _load_one(path: Path) -> bool:
    name = f"yuki_user_tools.{path.stem}"
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return True
    except Exception as e:
        log.warning("user tool %s failed to load: %s", path.name, e)
        return False


def load_user_tools() -> list[str]:
    """Import every .py file in the user tools dir; tolerate failures."""
    root = _user_tools_dir()
    if not root.exists():
        return []
    loaded: list[str] = []
    for path in sorted(root.glob("*.py")):
        before = set(REGISTRY.keys())
        if _load_one(path):
            after = set(REGISTRY.keys())
            if after != before:
                loaded.append(path.name)
    return loaded
