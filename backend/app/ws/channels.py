import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Callable

from app.core.logging import get_logger
from app.ws.manager import ws_manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    """
    语音交互通道。
    客户端连接后，以 JSON 消息双向交互：

    客户端 → 服务端:
      - {"type": "transcript", "text": "..."}
      - {"type": "intent_result", "intent": {...}}
      - {"type": "tts_end"}
      - {"type": "cancel"}

    服务端 → 客户端:
      - {"type": "transcript", "text": "..."}
      - {"type": "intent_parsed", "intent": {...}}
      - {"type": "clarification", "question": "..."}
      - {"type": "confirmation", "prompt": "...", "params": {...}}
      - {"type": "execution_started", "task_id": "..."}
      - {"type": "execution_completed", "task_id": "...", "result": {...}}
      - {"type": "execution_failed", "task_id": "...", "error": "..."}
      - {"type": "tts_start", "text": "..."}
      - {"type": "balance_update", "mass_mg": 12345, "stable": true}
      - {"type": "balance_over_limit", "mass_mg": 230000}
    """
    client_id = f"voice_{id(websocket)}"
    await ws_manager.connect(client_id, websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid JSON"})
                continue
            msg_type = msg.get("type", "")
            if msg_type == "cancel":
                await websocket.send_json({"type": "cancel_ack"})
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception:
        ws_manager.disconnect(client_id)


@router.websocket("/ws/balance")
async def balance_websocket(websocket: WebSocket) -> None:
    """
    天平实时数据通道。
    服务端持续推送天平读数（mg 整数），客户端只读。
    """
    client_id = f"balance_{id(websocket)}"
    await ws_manager.connect(client_id, websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
    except Exception:
        ws_manager.disconnect(client_id)


async def push_balance(mass_mg: int, stable: bool) -> None:
    await ws_manager.broadcast({
        "type": "balance_update",
        "mass_mg": mass_mg,
        "stable": stable,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def push_balance_over_limit(mass_mg: int) -> None:
    await ws_manager.broadcast({
        "type": "balance_over_limit",
        "mass_mg": mass_mg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
