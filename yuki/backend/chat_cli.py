"""Interactive chat REPL.

Run with:
    uv run python -m yuki.backend.chat_cli

Reads YUKI_AUTH_TOKEN, YUKI_PORT, YUKI_BACKEND_URL from env (or .env in cwd /
project root). Posts each line to /chat (or /chat/control with a /control
prefix) and streams the reply.

Slash commands:
    /control <task>   route this turn through the desktop agent
    /quit | /exit     leave the REPL
    /help             show this list
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

_DEFAULT_PORT = 8765


def _load_env_files() -> None:
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def _resolve_url() -> str:
    explicit = os.environ.get("YUKI_BACKEND_URL")
    if explicit:
        return explicit.rstrip("/")
    port = os.environ.get("YUKI_PORT", str(_DEFAULT_PORT))
    return f"http://127.0.0.1:{port}"


def _print_help() -> None:
    print(
        "\nCommands:\n"
        "  /control <task>   route this turn through the desktop agent (slow)\n"
        "  /help             show this list\n"
        "  /quit | /exit     leave the REPL\n"
        "  Ctrl+C            also leaves\n"
    )


def _post_chat(
    client: httpx.Client, base_url: str, token: str, message: str, *, control: bool
) -> str:
    """POST one message and return the final 'content'. Streams SSE under the hood."""
    path = "/chat/control" if control else "/chat"
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body: dict[str, object] = {"message": message}
    final_content = ""
    with client.stream(
        "POST", url, headers=headers, json=body, timeout=None
    ) as resp:
        if resp.status_code != 200:
            return f"[error {resp.status_code}] {resp.read().decode('utf-8', 'ignore')}"
        # SSE frames: lines starting with "event:" / "data:"; blank line separates.
        cur_event: str | None = None
        for raw in resp.iter_lines():
            line = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
            if line.startswith(":"):
                # comment / keepalive ping
                continue
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                payload = line.split(":", 1)[1].strip()
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                etype = obj.get("type") or cur_event or ""
                if etype == "done":
                    final_content = str(obj.get("content", ""))
                elif etype == "error":
                    return f"[error] {obj.get('content', '')}"
    return final_content or "[no content]"


def _check_backend(client: httpx.Client, base_url: str) -> tuple[bool, str]:
    try:
        r = client.get(f"{base_url}/healthz", timeout=2.0)
        return r.status_code == 200, r.text
    except httpx.HTTPError as e:
        return False, str(e)


def main() -> None:
    _load_env_files()
    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print(
            "YUKI_AUTH_TOKEN not set. Add it to .env or export it in your shell.",
            file=sys.stderr,
        )
        sys.exit(2)
    base_url = _resolve_url()

    with httpx.Client() as client:
        ok, detail = _check_backend(client, base_url)
        if not ok:
            print(
                f"yuki: backend not reachable at {base_url} ({detail})\n"
                f"Start it with `uv run python -m yuki.backend.cli` in another shell.",
                file=sys.stderr,
            )
            sys.exit(3)

        print(f"yuki: connected to {base_url}")
        print(
            "Type a message and press enter. /help for commands. Ctrl+D or /quit to exit."
        )

        while True:
            try:
                line = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                continue
            if line in ("/quit", "/exit"):
                return
            if line == "/help":
                _print_help()
                continue
            if line.startswith("/control "):
                msg = line[len("/control ") :].strip()
                if not msg:
                    print("[empty /control message]")
                    continue
                reply = _post_chat(client, base_url, token, msg, control=True)
            elif line.startswith("/"):
                print(f"[unknown command {line.split()[0]} — try /help]")
                continue
            else:
                reply = _post_chat(client, base_url, token, line, control=False)
            print(f"yuki> {reply}\n")


if __name__ == "__main__":
    main()
