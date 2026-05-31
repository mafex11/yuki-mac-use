"""POST /settings/provider — persist provider/model; GET tests connection."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from yuki.backend import appstate

router = APIRouter(prefix="/settings/provider", tags=["settings"])


class ProviderConfig(BaseModel):
    provider: str
    model: str | None = None


@router.post("")
async def set_provider(cfg: ProviderConfig) -> dict[str, str]:
    state = appstate.load()
    state["llm_provider"] = cfg.provider
    if cfg.model:
        state["llm_model"] = cfg.model
    appstate.save(state)
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
