from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DialogSession(Base):
    __tablename__ = "dialog_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    messages_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    round_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    @property
    def messages(self) -> list[dict]:
        import json

        try:
            value = json.loads(self.messages_json or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        import json

        self.messages_json = json.dumps(value or [], ensure_ascii=False)
