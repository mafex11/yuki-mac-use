"""FastAPI app factory + lifespan + auth dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from yuki.backend.auth import AuthError, verify
from yuki.backend.runtime import get_runtime, reset_runtime


def require_token(authorization: Annotated[str, Header()] = "") -> None:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        verify(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_runtime()
    yield
    reset_runtime()


def create_app() -> FastAPI:
    app = FastAPI(title="Yuki backend", lifespan=_lifespan)

    from yuki.backend.routers import (
        chat,
        health,
        memory,
        safety,
        scan,
        settings,
        tools,
        triggers,
    )

    # /healthz has no auth — menu-bar app polls it on startup.
    app.include_router(health.router)
    app.include_router(tools.router, dependencies=[Depends(require_token)])
    app.include_router(memory.router, dependencies=[Depends(require_token)])
    app.include_router(triggers.router, dependencies=[Depends(require_token)])
    app.include_router(settings.router, dependencies=[Depends(require_token)])
    app.include_router(scan.router, dependencies=[Depends(require_token)])
    app.include_router(safety.router, dependencies=[Depends(require_token)])
    app.include_router(chat.router, dependencies=[Depends(require_token)])

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app
