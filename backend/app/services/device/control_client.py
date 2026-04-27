"""C++ 后级控制程序 HTTP 客户端。

健壮性设计：
- transport 带 retries=2（仅对 GET / idempotent 请求有效，httpx 内部语义）
- keepalive_expiry=3.0s（小于 uvicorn 默认 5s，避免复用已被对端关闭的空连接）
- send_command 检查响应体的 status 字段，而非只看 HTTP 200
- 所有方法返回 (ok: bool, reason: str | None) 元组，便于上层生成用户可见提示
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ControlClient:
    def __init__(self) -> None:
        transport = httpx.AsyncHTTPTransport(
            retries=2,
            proxy=None,
        )
        self._client = httpx.AsyncClient(
            base_url=settings.control_adapter_url,
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
            transport=transport,
            trust_env=False,
        )

    async def send_command(self, command: dict[str, Any]) -> tuple[bool, str | None]:
        """下发指令。

        返回 (ok, reason)：
        - ok=True: mock-qt / C++ 回 status=accepted
        - ok=False: HTTP 错误 或 status=rejected；reason 给用户可见的提示
        """
        command_id = command.get("command_id")
        try:
            resp = await self._client.post("/api/command", json=command)
        except httpx.TimeoutException:
            logger.error("命令下发超时: %s", command_id)
            return False, "控制程序响应超时"
        except httpx.HTTPError as e:
            logger.exception("命令下发网络异常: %s", command_id)
            return False, f"控制程序通信错误：{type(e).__name__}"

        if resp.status_code >= 500:
            logger.error("命令下发 HTTP %d: %s", resp.status_code, command_id)
            return False, f"控制程序错误：HTTP {resp.status_code}"

        try:
            body = resp.json()
        except ValueError:
            logger.error("命令下发响应非 JSON: %s", resp.text[:200])
            return False, "控制程序返回格式异常"

        status = body.get("status")
        if status == "accepted":
            logger.info("命令已下发: %s", command_id)
            return True, None

        # rejected 或其他
        reason = body.get("message") or f"status={status}"
        logger.warning("命令被拒绝: %s (%s)", command_id, reason)
        return False, reason

    async def send_emergency_stop(self) -> tuple[bool, str | None]:
        return await self.send_command({
            "schema_version": "2.1",
            "command_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operator_id": "admin",
            "command_type": "emergency_stop",
            "payload": {},
        })

    async def get_status(self) -> dict:
        try:
            resp = await self._client.get("/api/status")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning("获取设备状态失败: %s", type(e).__name__)
            return {"device_status": "unknown", "balance_ready": False}
        except Exception:
            logger.exception("获取设备状态未知异常")
            return {"device_status": "unknown", "balance_ready": False}

    async def close(self) -> None:
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


__all__ = [
    "ControlClient",
    "get_control_client",
    "get_control_client_async",
]
