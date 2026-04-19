"""NetScope web backend — FastAPI app setup, lifespan, and live WebSocket feed.

All mutable state lives in ``state.py``.
The background ping worker is managed by ``ping_worker.py``.
The WebSocket payload is assembled by ``payload.py``.
Routes are split across ``routes/``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.version import read_version
from web.backend import payload as _payload
from web.backend import ping_worker
from web.backend.routes import diagnostics, info, sessions, wifi

log = logging.getLogger(__name__)
_APP_VERSION = read_version()

_FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
_INDEX_HTML = os.path.join(_FRONTEND, "index.html")

_bundle_ver_cache: str | None = None


def _frontend_js_bundle_ver() -> str:
    """Cache-bust query param when index or any frontend *.js changes (any depth)."""
    global _bundle_ver_cache
    if _bundle_ver_cache is not None:
        return _bundle_ver_cache
    try:
        mt = int(os.path.getmtime(_INDEX_HTML))
    except OSError:
        _bundle_ver_cache = "0"
        return _bundle_ver_cache
    try:
        for dirpath, _dirnames, filenames in os.walk(_FRONTEND):
            for name in filenames:
                if name.endswith(".js"):
                    p = os.path.join(dirpath, name)
                    if os.path.isfile(p):
                        mt = max(mt, int(os.path.getmtime(p)))
    except OSError:
        pass
    _bundle_ver_cache = str(mt)
    return _bundle_ver_cache


class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") and path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response


def _warm_wifi_sync() -> None:
    try:
        from collectors.wifi_collector import fetch_current_connection
        fetch_current_connection()
    except Exception:
        log.debug("Wi-Fi warm-up skipped", exc_info=True)


async def _warm_wifi_collector() -> None:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _warm_wifi_sync)
    except Exception:
        log.debug("Wi-Fi warm-up task failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    ping_worker.ensure_running()
    asyncio.create_task(_warm_wifi_collector())
    log.info("NetScope v%s web backend started", _APP_VERSION)
    yield
    ping_worker.stop()
    log.info("NetScope v%s web backend stopped", _APP_VERSION)


app = FastAPI(title="NetScope", version=_APP_VERSION, lifespan=lifespan)
app.add_middleware(_NoCacheStaticMiddleware)
app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")

app.include_router(sessions.router)
app.include_router(diagnostics.router)
app.include_router(wifi.router)
app.include_router(info.router)


@app.get("/")
async def index() -> HTMLResponse:
    try:
        raw = Path(_INDEX_HTML).read_text(encoding="utf-8")
    except OSError:
        return HTMLResponse(
            "<!DOCTYPE html><html><body>Missing index.html</body></html>",
            status_code=500,
        )
    body = raw.replace("__STATIC_V__", _frontend_js_bundle_ver())
    return HTMLResponse(body, headers={"Cache-Control": "no-store, max-age=0"})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(None, _payload.build)
            await ws.send_json(data)
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WebSocket feed error")
        try:
            await ws.close()
        except Exception:
            pass
