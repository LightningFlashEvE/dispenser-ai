from fastapi import WebSocket, WebSocketDisconnect
from typing import Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket 连接建立: {client_id}")

    def disconnect(self, client_id: str) -> None:
        self.active_connections.pop(client_id, None)
        logger.info(f"WebSocket 连接断开: {client_id}")

    async def send_json(self, client_id: str, data: dict) -> bool:
        websocket = self.active_connections.get(client_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            self.disconnect(client_id)
            return False

    async def broadcast(self, data: dict) -> None:
        for client_id in list(self.active_connections.keys()):
            await self.send_json(client_id, data)


ws_manager = ConnectionManager()
