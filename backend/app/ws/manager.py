import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self._send_locks: dict[str, asyncio.Lock] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self._send_locks[client_id] = asyncio.Lock()
        logger.info("WebSocket 连接建立: %s", client_id)

    def disconnect(self, client_id: str) -> None:
        self.active_connections.pop(client_id, None)
        self._send_locks.pop(client_id, None)
        logger.info("WebSocket 连接断开: %s", client_id)

    async def send_json(self, client_id: str, data: dict) -> bool:
        lock = self._send_locks.get(client_id)
        if lock is None:
            return False

        async with lock:
            websocket = self.active_connections.get(client_id)
            if websocket is None:
                return False

            try:
                await websocket.send_json(data)
                return True
            except Exception:
                logger.exception(
                    "WebSocket 发送失败 client_id=%s type=%s",
                    client_id,
                    data.get("type"),
                )
                self.disconnect(client_id)
                return False

    async def broadcast(self, data: dict) -> None:
        for client_id in list(self.active_connections.keys()):
            await self.send_json(client_id, data)


ws_manager = ConnectionManager()
