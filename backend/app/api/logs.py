from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/api/logs", tags=["操作日志"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[dict])
async def list_logs(
    db: DBSession,
    task_id: str | None = None,
    event_type: str | None = None,
    operator_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict]:
    """查询审计日志，仅支持读，不支持修改或删除。"""
    stmt = select(AuditLog)
    if task_id is not None:
        stmt = stmt.where(AuditLog.task_id == task_id)
    if event_type is not None:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if operator_id is not None:
        stmt = stmt.where(AuditLog.operator_id == operator_id)
    if start_time is not None:
        stmt = stmt.where(AuditLog.created_at >= start_time)
    if end_time is not None:
        stmt = stmt.where(AuditLog.created_at <= end_time)
    stmt = stmt.offset(skip).limit(limit).order_by(AuditLog.created_at.desc())
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "task_id": log.task_id,
            "operator_id": log.operator_id,
            "event_type": log.event_type,
            "detail": log.detail,
            "created_at": log.created_at,
        }
        for log in logs
    ]
