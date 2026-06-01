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
