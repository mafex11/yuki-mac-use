"""POST /settings/provider — persist provider/model; GET tests connection."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from yuki.backend import appstate

router = APIRouter(prefix="/settings/provider", tags=["settings"])


class ProviderConfig(BaseModel):
    provider: str
    model: str | None = None


class ProviderKey(BaseModel):
    provider: str
    key: str


@router.get("")
async def get_provider() -> dict[str, str]:
    state = appstate.load()
    return {
        "provider": str(state.get("llm_provider", "google")),
        "model": str(state.get("llm_model", "")),
    }


@router.post("")
async def set_provider(cfg: ProviderConfig) -> dict[str, str]:
    state = appstate.load()
    state["llm_provider"] = cfg.provider
    if cfg.model:
        state["llm_model"] = cfg.model
    appstate.save(state)
    return {"ok": "true"}


@router.post("/key")
async def set_key(body: ProviderKey) -> dict[str, str]:
    """Receive an api key from the trusted Swift app (read silently from the
    Keychain there) and cache it in-process. Avoids the headless backend
    shelling out to `security`, which blocks on a GUI ACL prompt.
    """
    appstate.set_runtime_key(body.provider, body.key)
    return {"ok": "true"}


# Curated tool-capable models Yuki recommends for local control. All support
# the Ollama "tools" capability (required for the desktop agent). Notes reflect
# measured reliability on Yuki's agent eval suite (graph_score, Tool RAG on, the
# 36-case set): qwen2.5:7b≈0.90, qwen2.5:3b=0.58, llama3.2:1b=0.10. Bigger = more
# reliable for control; smaller = faster but better suited to chat/simple tasks.
#
# Fine-tuning finding (see training/README.md): a narrow LoRA HELPS a weak base
# (llama3.2:1b 0.10 -> yuki-1b 0.28) but HURTS a strong one (qwen2.5:3b 0.58 ->
# yuki-3b 0.36, catastrophic forgetting). So we recommend STOCK qwen2.5:3b as the
# mid-tier, not a fine-tune, and keep yuki-1b only as a lightweight option.
_RECOMMENDED_OLLAMA: list[dict[str, str]] = [
    {"name": "qwen2.5:7b", "size": "~4.7 GB",
     "note": "Recommended — reliable Mac control (needs ~8GB RAM)"},
    {"name": "qwen2.5:3b", "size": "~1.9 GB",
     "note": "Good control, lighter; best mid-tier local option"},
    {"name": "llama3.2:3b", "size": "~2.0 GB",
     "note": "Well-rounded, tool-tuned; lighter than 7B"},
    {"name": "llama3.2:1b", "size": "~1.3 GB",
     "note": "Fastest; best for chat, not multi-step control"},
]

# Yuki's own fine-tunes (built via training/, not yet published to a registry).
# These are NOT pullable, so they're only surfaced as recommendations when the
# user already has them installed locally — appended in list_ollama_models().
# Only yuki-1b ships: fine-tuning improved the weak 1b but degraded the strong
# 3b (use stock qwen2.5:3b for that tier instead).
_YUKI_FINETUNES: dict[str, dict[str, str]] = {
    "yuki-1b": {"name": "yuki-1b", "size": "~2.5 GB",
                "note": "Yuki's own fine-tune of llama3.2:1b; fast, local, basic control"},
}


def _recommendations_for(installed_names: set[str]) -> list[dict[str, str]]:
    """Recommendations to show, given the locally-installed model names.

    Yuki's own fine-tunes aren't pullable from a registry yet, so they only
    appear when already installed (matched on the base name, ignoring any tag).
    They're listed first since they're the local-first default we tuned.
    """
    bases = {n.split(":")[0] for n in installed_names}
    extra = [meta for key, meta in _YUKI_FINETUNES.items() if key in bases]
    return extra + _RECOMMENDED_OLLAMA


def _model_supports_tools(client: object, name: str) -> bool:
    """True if the model exposes the Ollama 'tools' capability."""
    try:
        info = client.show(name)  # type: ignore[attr-defined]
        caps = getattr(info, "capabilities", None)
        if caps is None and isinstance(info, dict):
            caps = info.get("capabilities")
        return "tools" in (caps or [])
    except Exception:
        return False


@router.get("/ollama/models")
async def list_ollama_models() -> dict[str, object]:
    """List local Ollama models with tool-capability, plus recommendations.

    Returns {running, models: [{name, tools}], recommended: [{name,size,note}]}.
    `tools` flags whether the model can run control tasks (the desktop agent
    needs it); chat works on any model. running=False means Ollama isn't
    reachable, so the UI falls back to manual entry.
    """
    try:
        import ollama

        client = ollama.Client()
        resp = client.list()
        raw = getattr(resp, "models", resp)
        models: list[dict[str, object]] = []
        for m in raw:
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name is None and isinstance(m, dict):
                name = m.get("model") or m.get("name")
            if name:
                models.append(
                    {"name": str(name),
                     "tools": _model_supports_tools(client, str(name))}
                )
        # Surface Yuki's own fine-tunes as recommendations only when actually
        # installed locally (they aren't pullable from a registry yet).
        installed = {str(m["name"]) for m in models}
        return {"running": True, "models": models,
                "recommended": _recommendations_for(installed)}
    except Exception:
        return {"running": False, "models": [],
                "recommended": _RECOMMENDED_OLLAMA}


class PullRequest(BaseModel):
    model: str


@router.post("/ollama/pull")
async def pull_ollama_model(req: PullRequest) -> object:
    """Stream `ollama pull <model>` progress as SSE.

    Emits {type:"progress", percent:int, status:str} chunks and a final
    {type:"done"} or {type:"error", message:str}.
    """
    import json
    from collections.abc import AsyncIterator

    from sse_starlette.sse import EventSourceResponse

    async def _events() -> AsyncIterator[dict[str, str]]:
        import asyncio
        import threading

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        _SENTINEL = object()

        def _pull_worker() -> None:
            # ollama's client is sync + blocking; run the streaming pull in a
            # thread and hand each progress chunk to the async queue as it
            # arrives (don't buffer — that would defeat live progress).
            try:
                import ollama

                for ch in ollama.Client().pull(req.model, stream=True):
                    status = getattr(ch, "status", "") or ""
                    completed = getattr(ch, "completed", 0) or 0
                    total = getattr(ch, "total", 0) or 0
                    percent = int(completed * 100 / total) if total else 0
                    loop.call_soon_threadsafe(
                        queue.put_nowait, ("progress", percent, status))
                loop.call_soon_threadsafe(queue.put_nowait, (_SENTINEL, 0, ""))
            except Exception as e:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", 0, str(e)))

        threading.Thread(target=_pull_worker, daemon=True).start()

        last = -1
        while True:
            kind, percent, text = await queue.get()
            if kind is _SENTINEL:
                yield {"event": "done", "data": json.dumps({"type": "done"})}
                return
            if kind == "error":
                yield {"event": "error", "data": json.dumps(
                    {"type": "error", "message": text})}
                return
            if percent != last or text:
                last = percent
                yield {"event": "progress", "data": json.dumps(
                    {"type": "progress", "percent": percent, "status": text})}

    return EventSourceResponse(_events())


@router.get("/test")
async def test_provider() -> dict[str, bool]:
    try:
        from yuki.messages import HumanMessage
        from yuki.providers.factory import make_llm
        llm = make_llm()
        ev = await llm.ainvoke(messages=[HumanMessage(content="ping")], tools=[])
        return {"ok": bool(ev and (ev.content or "").strip())}
    except Exception:
        return {"ok": False}
