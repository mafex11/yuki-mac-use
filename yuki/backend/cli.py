"""CLI entry point: `python -m yuki.backend.cli` starts the FastAPI server.

Auto-loads .env from the current working directory and from the project root
(parent of yuki/) so `uv run python -m yuki.backend.cli` picks up local config
without forcing the user to source .env into their shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from yuki.backend.auth import set_active_token
from yuki.backend.server import create_app


def _load_env_files() -> list[Path]:
    """Load .env from cwd and project root. Existing env vars take precedence."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    seen: set[Path] = set()
    loaded: list[Path] = []
    for path in candidates:
        if path in seen or not path.exists():
            seen.add(path)
            continue
        seen.add(path)
        # override=False: real env vars win, .env fills gaps.
        load_dotenv(path, override=False)
        loaded.append(path)
    return loaded


def main() -> None:
    loaded = _load_env_files()
    if loaded:
        print(
            f"yuki: loaded env from {', '.join(str(p) for p in loaded)}",
            file=sys.stderr,
        )

    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print(
            "YUKI_AUTH_TOKEN env var is required.\n"
            "Add it to .env (in cwd or project root) or export it in your shell:\n"
            "  echo \"YUKI_AUTH_TOKEN=$(python3 -c 'import secrets; "
            "print(secrets.token_hex(32))')\" >> .env",
            file=sys.stderr,
        )
        sys.exit(2)
    set_active_token(token)
    port = int(os.environ.get("YUKI_PORT", "0"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
