from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.draft_manager import draft_manager

router = APIRouter(prefix="/debug", tags=["debug"])


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

