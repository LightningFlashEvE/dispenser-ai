"""
manual.py — 手动控制接口

POST /api/manual/command

前端手动控制面板直接组装合法 command JSON 并提交到此接口。
流程：前端 payload → 此接口补全 command 外壳 → 规则/状态机校验 → 控制客户端下发。
注意：手动模式绕过 LLM，但不绕过状态机和控制白名单。
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.task import Task
from app.services.device.control_client import get_control_client
from app.services.dialog.state_machine import get_state_machine

logger = get_logger(__name__)
router = APIRouter(prefix="/api/manual", tags=["手动控制"])

DBSession = Annotated[AsyncSession, Depends(get_db)]

VALID_COMMAND_TYPES = {
    "dispense", "aliquot", "mix", "formula",
    "restock", "cancel", "emergency_stop", "device_status",
}

COMMANDS_REQUIRING_CONFIRMATION = {
    "dispense", "aliquot", "mix", "formula", "restock",
}


class ManualCommandRequest(BaseModel):
    command_type: str
    payload: dict[str, Any]

    @field_validator("command_type")
    @classmethod
    def validate_command_type(cls, v: str) -> str:
        if v not in VALID_COMMAND_TYPES:
            raise ValueError(f"不支持的指令类型: {v}，合法值: {sorted(VALID_COMMAND_TYPES)}")
        return v


@router.post("/command", status_code=status.HTTP_200_OK)
async def manual_command(
    db: DBSession,
    req: ManualCommandRequest,
) -> dict:
    """
    手动下发合法 command JSON。
    - 不经过 LLM，但必须经过状态机校验
    - 需要确认的指令类型（dispense/aliquot/mix/formula/restock）统一以 screen 确认
    - emergency_stop 和 cancel 不受状态机 can_start_task 限制
    """
    state_machine = get_state_machine()
    control_client = get_control_client()
    now = datetime.now(timezone.utc)

    # ── 状态机检查（急停和取消例外）──────────────────────────────
    if req.command_type not in {"emergency_stop", "cancel", "device_status"}:
        can_start, reason = state_machine.can_start_task()
        if not can_start:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"设备当前无法接受新任务：{reason}",
            )

    # ── 构建完整 command ──────────────────────────────────────────
    command_id = str(uuid.uuid4())
    command: dict[str, Any] = {
        "schema_version": "2.1",
        "command_id": command_id,
        "timestamp": now.isoformat(),
        "operator_id": "admin",
        "command_type": req.command_type,
        "payload": req.payload,
    }

    if req.command_type in COMMANDS_REQUIRING_CONFIRMATION and not settings.skip_confirmation:
        command["confirmation"] = {
            "method": "screen",
            "confirmed_at": now.isoformat(),
        }

    # ── 急停特殊处理 ──────────────────────────────────────────────
    if req.command_type == "emergency_stop":
        state_machine.trigger_emergency_stop()
        ok, reason = await control_client.send_emergency_stop()
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"急停指令下发失败：{reason or '请检查控制程序连接'}",
            )
        logger.warning("手动急停指令已下发 command_id=%s", command_id)
        return {"command_id": command_id, "task_id": None, "status": "sent"}

    # ── 查询设备状态特殊处理 ──────────────────────────────────────
    if req.command_type == "device_status":
        device_status = await control_client.get_status()
        return {"command_id": command_id, "task_id": None, "status": "ok", "device_status": device_status}

    # ── 落库并下发 ────────────────────────────────────────────────
    task_id = str(uuid.uuid4())
    task = Task(
        task_id=task_id,
        command_id=command_id,
        command_type=req.command_type,
        operator_id="admin",
        status="EXECUTING",
        intent_json=json.dumps({"manual": True, "command_type": req.command_type}, ensure_ascii=False),
        command_json=json.dumps(command, ensure_ascii=False),
        started_at=now,
    )
    db.add(task)
    await db.commit()

    ok, reason = await control_client.send_command(command)
    if not ok:
        task.status = "FAILED"
        task.error_message = reason or "控制程序连接失败，指令未能下发"
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"指令下发失败：{reason or '请检查 C++ 控制程序连接状态'}",
        )

    if req.command_type != "cancel":
        state_machine.start_task(task_id)

    logger.info("手动指令已下发 command_type=%s command_id=%s task_id=%s", req.command_type, command_id, task_id)
    return {"command_id": command_id, "task_id": task_id, "status": "sent"}
