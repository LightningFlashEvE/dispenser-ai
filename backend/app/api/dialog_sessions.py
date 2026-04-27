import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.dialog_session import DialogSession

router = APIRouter(prefix="/api/dialog-sessions", tags=["对话会话"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionListItem(BaseModel):
    session_id: str
    title: str
    message_count: int
    round_count: int
    created_at: str
    updated_at: str


class SessionDetail(BaseModel):
    session_id: str
    title: str
    messages: list[dict]
    round_count: int
    task_id: str | None
    created_at: str
    updated_at: str


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionUpdateRequest(BaseModel):
    messages: list[dict]
    round_count: int | None = None


DBSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    db: DBSession,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[DialogSession]:
    stmt = (
        select(DialogSession)
        .order_by(desc(DialogSession.updated_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())
    return [
        SessionListItem(
            session_id=s.session_id,
            title=_derive_title(s.messages),
            message_count=len(s.messages),
            round_count=s.round_count,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(db: DBSession, session_id: str) -> SessionDetail:
    stmt = select(DialogSession).where(DialogSession.session_id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return SessionDetail(
        session_id=session.session_id,
        title=_derive_title(session.messages),
        messages=session.messages,
        round_count=session.round_count,
        task_id=session.task_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.post("", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session(db: DBSession) -> SessionCreateResponse:
    session_id = str(uuid.uuid4())
    session = DialogSession(
        session_id=session_id,
        messages_json="[]",
        round_count=0,
    )
    db.add(session)
    await db.commit()
    return SessionCreateResponse(session_id=session_id)


@router.patch("/{session_id}")
async def update_session(
    db: DBSession,
    session_id: str,
    body: SessionUpdateRequest,
) -> dict:
    stmt = select(DialogSession).where(DialogSession.session_id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    session.messages = body.messages
    if body.round_count is not None:
        session.round_count = body.round_count
    session.updated_at = _utcnow()
    await db.commit()
    return {"ok": True}


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(db: DBSession, session_id: str) -> None:
    stmt = select(DialogSession).where(DialogSession.session_id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    await db.delete(session)
    await db.commit()


def _derive_title(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "") or msg.get("text", "")
            if text:
                return text[:40] + ("..." if len(text) > 40 else "")
    return "新对话"
