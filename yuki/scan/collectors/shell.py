"""Shell history collector — command frequency from zsh/bash history."""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

_ZSH_PREFIX = re.compile(r"^:\s*\d+:\d+;")


class ShellCollector:
    name = "shell"

    async def collect(self) -> list[dict[str, Any]]:
        home = Path(os.environ["HOME"])
        for candidate in (".zsh_history", ".bash_history"):
            path = home / candidate
            if path.exists():
                return self._parse(path)
        return []

    def _parse(self, path: Path) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        for raw_line in text.splitlines():
            line = _ZSH_PREFIX.sub("", raw_line).strip()
            if not line:
                continue
            cmd = line.split(maxsplit=1)[0]
            counts[cmd] += 1
        return [{"command": c, "count": n} for c, n in counts.most_common()]
