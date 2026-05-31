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


def _watch_parent_death() -> None:
    """Exit when the spawning parent (Swift app) dies. macOS lacks
    PR_SET_PDEATHSIG, so poll getppid(): re-parenting to launchd (pid 1)
    means our parent is gone."""
    import os
    import threading
    import time

    original_ppid = os.getppid()

    def _poll() -> None:
        while True:
            time.sleep(2)
            if os.getppid() != original_ppid or os.getppid() == 1:
                os._exit(0)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


def main() -> None:
    import argparse
    from yuki.backend import auth
    from yuki.memory import paths

    parser = argparse.ArgumentParser()
    parser.add_argument("--uds", action="store_true",
                        help="bind a Unix Domain Socket instead of TCP")
    args = parser.parse_args()

    loaded = _load_env_files()
    if loaded:
        print(
            f"yuki: loaded env from {', '.join(str(p) for p in loaded)}",
            file=sys.stderr,
        )

    if args.uds:
        auth.set_uds_mode(True)
        sock = paths.socket_path()
        sock.parent.mkdir(parents=True, exist_ok=True)
        if sock.exists():
            sock.unlink()
        _watch_parent_death()
        print(f"yuki: backend listening on UDS {sock}", file=sys.stderr)
        uvicorn.run(create_app(), uds=str(sock), log_level="info")
        return

    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print("YUKI_AUTH_TOKEN env var is required for TCP mode.", file=sys.stderr)
        sys.exit(2)
    set_active_token(token)
    port = int(os.environ.get("YUKI_PORT", "0"))
    if port:
        print(
            f"yuki: backend listening on http://127.0.0.1:{port}",
            file=sys.stderr,
        )
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
