from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogRead

router = APIRouter(prefix="/api/logs", tags=["操作日志"])

DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[AuditLogRead])
async def list_logs(
    db: DBSession,
    task_id: str | None = None,
    event_type: str | None = None,
    operator_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AuditLogRead]:
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
    return [AuditLogRead.model_validate(log) for log in logs]
