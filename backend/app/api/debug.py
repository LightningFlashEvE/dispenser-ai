from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.draft_manager import draft_manager

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/drafts")
async def list_drafts() -> dict:
    if not settings.is_development:
        raise HTTPException(status_code=403, detail="debug endpoints are disabled")

    return {
        "drafts": [
            {
                "draft_id": draft.draft_id,
                "session_id": draft.session_id,
                "task_type": draft.task_type.value,
                "status": draft.status.value,
                "complete": draft.complete,
                "missing_slots": draft.missing_slots,
                "ready_for_review": draft.ready_for_review,
                "created_at": draft.created_at.isoformat(),
                "updated_at": draft.updated_at.isoformat(),
                "confirmed_at": draft.confirmed_at.isoformat() if draft.confirmed_at else None,
                "cancelled_at": draft.cancelled_at.isoformat() if draft.cancelled_at else None,
            }
            for draft in draft_manager.list_drafts()
        ]
    }


@router.get("/drafts/{draft_id}/events")
async def get_draft_events(draft_id: str) -> dict:
    if not settings.is_development:
        raise HTTPException(status_code=403, detail="debug endpoints are disabled")

    draft = draft_manager.get_by_draft_id(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")

    return {
        "draft_id": draft.draft_id,
        "session_id": draft.session_id,
        "task_type": draft.task_type.value,
        "status": draft.status.value,
        "events": [event.model_dump(mode="json") for event in draft.events],
    }


@router.post("/drafts/expire-stale")
async def expire_stale_drafts() -> dict:
    if not settings.is_development:
        raise HTTPException(status_code=403, detail="debug endpoints are disabled")

    expired = draft_manager.expire_stale()
    return {
        "expired_count": len(expired),
        "draft_ids": [draft.draft_id for draft in expired],
    }
