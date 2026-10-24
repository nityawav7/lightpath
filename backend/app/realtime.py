"""WebSocket fan-out of network snapshots to connected dashboards."""

from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

from .controller import NetworkController
from .schemas import snapshot

log = logging.getLogger("lightpath.realtime")


class SnapshotHub:
    def __init__(self, controller: NetworkController, max_clients: int = 200) -> None:
        self._controller = controller
        self._clients: set[WebSocket] = set()
        self._max_clients = max_clients
        self._send_lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> bool:
        await ws.accept()
        if len(self._clients) >= self._max_clients:
            await ws.close(code=1013, reason="server busy")
            return False
        self._clients.add(ws)
        await ws.send_text(self._payload())
        return True

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def _payload(self) -> str:
        return '{"type":"snapshot","data":' + snapshot(self._controller).model_dump_json() + "}"

    async def publish(self) -> None:
        if not self._clients:
            return
        async with self._send_lock:
            payload = self._payload()
            clients = list(self._clients)
            results = await asyncio.gather(
                *(asyncio.wait_for(ws.send_text(payload), timeout=5) for ws in clients),
                return_exceptions=True,
            )
            for ws, res in zip(clients, results, strict=True):
                if isinstance(res, Exception):
                    log.debug("dropping websocket client: %r", res)
                    self._clients.discard(ws)
