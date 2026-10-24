"""Application entry point: wires the controller, API, WebSocket and UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from . import __version__
from .api import router
from .config import Settings
from .controller import ControllerError, NetworkController
from .ratelimit import RateLimitMiddleware
from .realtime import SnapshotHub

log = logging.getLogger("lightpath")


async def _telemetry_loop(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    controller: NetworkController = app.state.controller
    hub: SnapshotHub = app.state.hub
    while True:
        await asyncio.sleep(settings.telemetry_interval_s)
        try:
            controller.tick_telemetry()
            await hub.publish()
        except Exception:  # keep the loop alive no matter what
            log.exception("telemetry tick failed")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(_telemetry_loop(app))
        log.info("LightPath %s started", __version__)
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="LightPath Optical Network Controller",
        version=__version__,
        description=(
            "Software-defined controller for a DWDM optical transport network: "
            "routing & wavelength assignment, 1+1 protection, fiber-cut restoration, "
            "alarms and optical telemetry."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.controller = NetworkController(settings)
    app.state.hub = SnapshotHub(app.state.controller)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.exception_handler(ControllerError)
    async def controller_error(_: Request, exc: ControllerError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    app.include_router(router)

    @app.websocket("/ws")
    async def websocket(ws: WebSocket) -> None:
        hub: SnapshotHub = app.state.hub
        if not await hub.connect(ws):
            return
        try:
            while True:
                # Clients only listen; reading keeps the connection healthy and
                # lets us notice disconnects promptly.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(ws)

    static_dir = settings.static_dir
    if static_dir and (static_dir / "index.html").is_file():
        root = static_dir.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "ws")):
                raise HTTPException(status_code=404)
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_file() and root in candidate.parents:
                headers = {}
                if "/assets/" in candidate.as_posix():
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return FileResponse(candidate, headers=headers)
            return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        log.info("No built UI found (STATIC_DIR unset); serving API only")

    return app


app = create_app()
