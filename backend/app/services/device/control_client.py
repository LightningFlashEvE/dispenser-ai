import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ControlClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.control_adapter_url,
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def send_command(self, command: dict[str, Any]) -> bool:
        try:
            resp = await self._client.post("/api/command", json=command)
            resp.raise_for_status()
            logger.info("命令已下发: %s", command.get("command_id"))
            return True
        except httpx.TimeoutException:
            logger.error("命令下发超时: %s", command.get("command_id"))
            return False
        except httpx.HTTPStatusError as e:
            logger.error("命令下发失败: %s, 状态码=%d", command.get("command_id"), e.response.status_code)
            return False
        except Exception:
            logger.exception("命令下发异常: %s", command.get("command_id"))
            return False

    async def get_status(self) -> dict:
        try:
            resp = await self._client.get("/api/status")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.exception("获取设备状态失败")
            return {"device_status": "unknown", "balance_ready": False}

    async def send_emergency_stop(self) -> bool:
        try:
            resp = await self._client.post("/api/command", json={
                "command_type": "emergency_stop",
                "payload": {}
            })
            resp.raise_for_status()
            logger.info("急停指令已下发")
            return True
        except Exception:
            logger.exception("急停指令下发失败")
            return False

    async def close(self):
        await self._client.aclose()


_control_client: ControlClient | None = None
_cc_lock: asyncio.Lock | None = None


def _get_cc_lock() -> asyncio.Lock:
    global _cc_lock
    if _cc_lock is None:
        _cc_lock = asyncio.Lock()
    return _cc_lock


async def get_control_client_async() -> ControlClient:
    global _control_client
    if _control_client is not None:
        return _control_client
    async with _get_cc_lock():
        if _control_client is None:
            _control_client = ControlClient()
    return _control_client


def get_control_client() -> ControlClient:
    global _control_client
    if _control_client is None:
        _control_client = ControlClient()
    return _control_client
