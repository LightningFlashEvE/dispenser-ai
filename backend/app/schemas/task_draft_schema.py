from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    WEIGHING = "WEIGHING"
    MIXING = "MIXING"
    DISPENSING = "DISPENSING"


class DraftStatus(str, Enum):
    NORMAL_CHAT = "NORMAL_CHAT"
    COLLECTING = "COLLECTING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    VERIFYING = "VERIFYING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVED = "APPROVED"
    COMMAND_SIGNED = "COMMAND_SIGNED"
    DISPATCHED = "DISPATCHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DraftValidationResult(BaseModel):
    complete: bool
    missing_slots: list[str] = Field(default_factory=list)
    ready_for_review: bool = False
    errors: list[str] = Field(default_factory=list)


class DraftEvent(BaseModel):
    event_type: str
    draft_id: str
    session_id: str
    user_message: str | None = None
    ai_patch: dict[str, Any] | None = None
    applied_patch: dict[str, Any] | None = None
    missing_slots: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskDraftRecord(BaseModel):
    draft_id: str
    session_id: str
    task_type: TaskType
    status: DraftStatus = DraftStatus.COLLECTING
    complete: bool = False
    missing_slots: list[str] = Field(default_factory=list)
    ready_for_review: bool = False
    current_draft: dict[str, Any] = Field(default_factory=dict)
    proposal_intent: dict[str, Any] | None = None
    events: list[DraftEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
