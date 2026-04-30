from __future__ import annotations

import asyncio
import json
import logging

import websockets

from app.core.config import settings
from app.ws.channels import push_balance

logger = logging.getLogger(__name__)

_stream_task: asyncio.Task | None = None


async def _weight_stream_loop() -> None:
    url = f"{settings.control_adapter_ws_url}/ws/weight"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                logger.info("已连接 mock-qt 重量流：%s", url)
                async for raw_msg in websocket:
                    try:
                        payload = json.loads(raw_msg)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("type") != "weight":
                        continue
                    value_mg = payload.get("value_mg")
                    if value_mg is None:
                        continue
                    stable = bool(payload.get("stable", False))
                    await push_balance(float(value_mg), stable)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("mock-qt 重量流断开，1s 后重连：%s", exc)
            await asyncio.sleep(1.0)


async def start_weight_stream() -> None:
    global _stream_task
    if _stream_task is None or _stream_task.done():
        _stream_task = asyncio.create_task(_weight_stream_loop())


async def stop_weight_stream() -> None:
    global _stream_task
    if _stream_task is None:
        return
    _stream_task.cancel()
    try:
        await _stream_task
    except asyncio.CancelledError:
        pass
    _stream_task = None
