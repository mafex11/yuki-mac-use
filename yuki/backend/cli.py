"""CLI entry point: `python -m yuki.backend.cli` starts the FastAPI server."""

from __future__ import annotations

import os
import sys

import uvicorn

from yuki.backend.auth import set_active_token
from yuki.backend.server import create_app


def main() -> None:
    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print("YUKI_AUTH_TOKEN env var is required", file=sys.stderr)
        sys.exit(2)
    set_active_token(token)
    port = int(os.environ.get("YUKI_PORT", "0"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
