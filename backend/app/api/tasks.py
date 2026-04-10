from datetime import datetime, timezone
from typing import Annotated

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import Task, TaskStep
from app.schemas.task import DeviceCallbackPayload, TaskRead, TaskStepRead
from app.services.dialog.state_machine import get_state_machine
from app.ws.manager import ws_manager

router = APIRouter(prefix="/api/tasks", tags=["任务管理"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    db: DBSession,
    status_filter: str | None = Query(default=None, alias="status"),
    operator_id: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Task]:
    stmt = select(Task)
    if status_filter is not None:
        stmt = stmt.where(Task.status == status_filter)
    if operator_id is not None:
        stmt = stmt.where(Task.operator_id == operator_id)
    stmt = stmt.offset(skip).limit(limit).order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(db: DBSession, task_id: str) -> Task:
    stmt = select(Task).where(Task.task_id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


@router.post("/callback", status_code=status.HTTP_200_OK)
async def device_callback(db: DBSession, payload: DeviceCallbackPayload) -> dict:
    """
    C++ 后级控制程序回调，接收执行结果。
    根据 command_id 找到对应任务，更新状态和结果。
    """
    stmt = (
        update(Task)
        .where(Task.command_id == payload.command_id)
        .values(
            result_json=json.dumps(payload.result, ensure_ascii=False) if payload.result else None,
            status=payload.status.upper(),
            completed_at=payload.completed_at,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    await db.commit()

    task_row = await db.execute(select(Task).where(Task.command_id == payload.command_id))
    matched_task = task_row.scalar_one_or_none()
    task_id_for_sm = matched_task.task_id if matched_task else None

    state_machine = get_state_machine()
    normalized_status = payload.status.lower()
    if task_id_for_sm and state_machine.current_task_id == task_id_for_sm:
        if normalized_status == "completed":
            state_machine.complete_task(task_id_for_sm)
        elif normalized_status == "failed":
            state_machine.fail_task(task_id_for_sm, payload.error.get("message", "任务失败") if payload.error else "任务失败")
        elif normalized_status == "cancelled":
            state_machine.cancel_task(task_id_for_sm)

    await ws_manager.broadcast(
        {
            "type": "command_result",
            "data": {
                "command_id": payload.command_id,
                "status": normalized_status,
                "result": payload.result,
                "error": payload.error,
                "completed_at": payload.completed_at.isoformat(),
            },
        }
    )
    await ws_manager.broadcast({"type": "state_change", "state": "FEEDBACK"})
    return {"received": True}


@router.patch("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(db: DBSession, task_id: str) -> Task:
    """取消任务，仅允许 PENDING / CONFIRMED 状态的任务。"""
    stmt = select(Task).where(Task.task_id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if task.status not in ("PENDING", "CONFIRMED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务状态为 {task.status}，不可取消",
        )
    task.status = "CANCELLED"
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return task
