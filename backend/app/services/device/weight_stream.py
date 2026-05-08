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
    retry_delay = 1.0
    max_delay = 30.0
    connected = False
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                if not connected:
                    logger.info("已连接 mock-qt 重量流：%s", url)
                    connected = True
                retry_delay = 1.0
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
                    timestamp = payload.get("timestamp")
                    await push_balance(float(value_mg), stable, timestamp if isinstance(timestamp, str) else None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            connected = False
            logger.warning("mock-qt 重量流断开，%.0fs 后重连：%s", retry_delay, exc)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


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
