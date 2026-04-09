import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._main_loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        logger.info("WS client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._clients))

    async def broadcast(self, topic: str, data: object) -> None:
        if not self._clients:
            return
        payload = json.dumps({"topic": topic, "data": data})
        dead: set[WebSocket] = set()
        for client in list(self._clients):
            try:
                await client.send_text(payload)
            except Exception:
                dead.add(client)
        for client in dead:
            self._clients.discard(client)

    def broadcast_from_thread(self, topic: str, data: object) -> None:
        """Thread-safe broadcast from worker threads onto the main event loop."""
        if self._main_loop and not self._main_loop.is_closed() and self._clients:
            asyncio.run_coroutine_threadsafe(
                self.broadcast(topic, data), self._main_loop
            )


ws_manager = ConnectionManager()
