"""Interactive chat REPL.

Run with:
    uv run python -m yuki.backend.chat_cli

Reads YUKI_AUTH_TOKEN, YUKI_PORT, YUKI_BACKEND_URL from env (or .env in cwd /
project root). Posts each line to /chat (or /chat/control with a /control
prefix) and streams the reply.

Slash commands:
    /control <task>   route this turn through the desktop agent
    /compact          summarize history; reduces context % usage
    /clear            wipe history; resets context to 0%
    /status           show current context usage
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
        "  /compact          summarize history (frees context %)\n"
        "  /clear            wipe history (back to 0%)\n"
        "  /status           show current context usage\n"
        "  /help             show this list\n"
        "  /quit | /exit     leave the REPL\n"
        "  Ctrl+C            also leaves\n"
    )


def _post_chat(
    client: httpx.Client, base_url: str, token: str, message: str, *, control: bool
) -> tuple[str, str]:
    """POST one message; return (final content, ctx_badge). Streams SSE."""
    path = "/chat/control" if control else "/chat"
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body: dict[str, object] = {"message": message}
    final_content = ""
    badge = ""
    with client.stream(
        "POST", url, headers=headers, json=body, timeout=None
    ) as resp:
        if resp.status_code != 200:
            err = f"[error {resp.status_code}] {resp.read().decode('utf-8', 'ignore')}"
            return err, ""
        cur_event: str | None = None
        for raw in resp.iter_lines():
            line = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
            if line.startswith(":"):
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
                    badge = str(obj.get("ctx_badge", ""))
                elif etype == "error":
                    return f"[error] {obj.get('content', '')}", ""
    return (final_content or "[no content]"), badge


def _post_simple(
    client: httpx.Client, base_url: str, token: str, path: str
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = client.post(f"{base_url}{path}", headers=headers, timeout=120.0)
    except httpx.HTTPError as e:
        return {"error": str(e)}
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text}"}
    try:
        return r.json()
    except Exception:
        return {"error": "non-json response"}


def _get_status(
    client: httpx.Client, base_url: str, token: str
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = client.get(f"{base_url}/chat/status", headers=headers, timeout=5.0)
    except httpx.HTTPError as e:
        return {"error": str(e)}
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text}"}
    try:
        return r.json()
    except Exception:
        return {"error": "non-json response"}


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
        status = _get_status(client, base_url, token)
        if "ctx_badge" in status:
            print(f"  {status['ctx_badge']}")
        print(
            "Type a message and press enter. /help for commands. "
            "Ctrl+D or /quit to exit."
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
            if line == "/status":
                st = _get_status(client, base_url, token)
                if "error" in st:
                    print(f"[error] {st['error']}\n")
                else:
                    print(f"  {st.get('ctx_badge', '?')}\n")
                continue
            if line == "/compact":
                print("compacting...", flush=True)
                resp = _post_simple(client, base_url, token, "/chat/compact")
                if "error" in resp:
                    print(f"[error] {resp['error']}\n")
                else:
                    print(f"  {resp.get('ctx_badge', '?')}\n")
                continue
            if line == "/clear":
                resp = _post_simple(client, base_url, token, "/chat/clear")
                if "error" in resp:
                    print(f"[error] {resp['error']}\n")
                else:
                    print(f"  history cleared {resp.get('ctx_badge', '')}\n")
                continue
            if line.startswith("/control "):
                msg = line[len("/control ") :].strip()
                if not msg:
                    print("[empty /control message]")
                    continue
                reply, badge = _post_chat(client, base_url, token, msg, control=True)
            elif line.startswith("/"):
                print(f"[unknown command {line.split()[0]} — try /help]")
                continue
            else:
                reply, badge = _post_chat(client, base_url, token, line, control=False)
            print(f"yuki> {reply}")
            if badge:
                print(f"  {badge}")
            print()


if __name__ == "__main__":
    main()
