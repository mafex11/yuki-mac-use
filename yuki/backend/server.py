"""FastAPI app factory + lifespan + auth dependency."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from yuki.backend.auth import AuthError, verify
from yuki.backend.runtime import get_runtime, reset_runtime

log = logging.getLogger("yuki")


def require_token(authorization: Annotated[str, Header()] = "") -> None:
    from yuki.backend import auth
    if auth.is_uds_mode():
        return
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        verify(token)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


def _build_observer():
    """Build the observer Daemon if YUKI_OBSERVER=1 (default off)."""
    if os.environ.get("YUKI_OBSERVER", "0") != "1":
        return None
    try:
        from yuki.observer.daemon import Daemon
        from yuki.observer.sources.idle import IdleSource
        from yuki.observer.sources.window import WindowSource
    except Exception as e:
        log.warning("observer disabled: import failed: %s", e)
        return None
    return Daemon(sources=[WindowSource(), IdleSource()])


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_runtime()
    try:
        from yuki.migrations import run_migrations
        run_migrations()
    except Exception as e:
        log.warning("migrations failed: %s", e)
    daemon = _build_observer()
    if daemon is not None:
        try:
            await daemon.start()
            log.info("yuki: observer started (window + idle sources)")
        except Exception as e:
            log.warning("yuki: observer failed to start: %s", e)
            daemon = None
    try:
        yield
    finally:
        if daemon is not None:
            try:
                await daemon.stop()
                log.info("yuki: observer stopped, events flushed")
            except Exception as e:
                log.warning("yuki: observer stop failed: %s", e)
        reset_runtime()


def create_app() -> FastAPI:
    app = FastAPI(title="Yuki backend", lifespan=_lifespan)

    from yuki.backend.routers import (
        chat,
        facts,
        health,
        memory,
        provider,
        route,
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
    app.include_router(facts.router, dependencies=[Depends(require_token)])
    app.include_router(triggers.router, dependencies=[Depends(require_token)])
    app.include_router(settings.router, dependencies=[Depends(require_token)])
    app.include_router(scan.router, dependencies=[Depends(require_token)])
    app.include_router(safety.router, dependencies=[Depends(require_token)])
    app.include_router(chat.router, dependencies=[Depends(require_token)])
    app.include_router(route.router, dependencies=[Depends(require_token)])
    app.include_router(provider.router, dependencies=[Depends(require_token)])

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app
