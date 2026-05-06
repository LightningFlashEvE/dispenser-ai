from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.task_draft_schema import DraftEvent, DraftStatus, TaskDraftRecord, TaskType
from app.schemas.weighing_draft_schema import WEIGHING_DRAFT_DEFAULT
from app.services.proposal_adapter import weighing_draft_to_legacy_dispense_intent
from app.validators.dispensing_validator import validate_dispensing_draft
from app.validators.mixing_validator import validate_mixing_draft
from app.validators.weighing_validator import validate_weighing_draft


class DraftManager:
    """In-memory task draft store.

    The AI only supplies a field patch. This manager owns state, merging,
    validation, and conversion to a formal backend intent proposal.
    """

    def __init__(self) -> None:
        self._drafts_by_session: dict[str, TaskDraftRecord] = {}

    def get_active(self, session_id: str) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft and draft.status in (DraftStatus.COLLECTING, DraftStatus.READY_FOR_REVIEW):
            return draft
        return None

    def get_by_draft_id(self, draft_id: str) -> TaskDraftRecord | None:
        for draft in self._drafts_by_session.values():
            if draft.draft_id == draft_id:
                return draft
        return None

    def start(self, session_id: str, task_type: TaskType) -> TaskDraftRecord:
        if task_type != TaskType.WEIGHING:
            raise ValueError("Only WEIGHING drafts are supported in phase 1")

        draft = TaskDraftRecord(
            draft_id=f"draft_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            task_type=task_type,
            current_draft=dict(WEIGHING_DRAFT_DEFAULT),
        )
        self._drafts_by_session[session_id] = self._validate_and_stamp(draft)
        self.record_event(draft, "draft_created")
        return self._drafts_by_session[session_id]

    def apply_patch(
        self,
        session_id: str,
        task_type: TaskType,
        patch: dict[str, Any],
        *,
        user_message: str | None = None,
        ai_patch: dict[str, Any] | None = None,
    ) -> TaskDraftRecord:
        draft = self.get_active(session_id)
        if draft is None:
            draft = self.start(session_id, task_type)
        elif draft.task_type != task_type:
            draft = self.start(session_id, task_type)

        applied_patch: dict[str, Any] = {}
        for key, value in patch.items():
            if key == "task_type":
                continue
            if value is None or value == "":
                continue
            if key in draft.current_draft:
                draft.current_draft[key] = value
                applied_patch[key] = value

        draft = self._validate_and_stamp(draft)
        self.record_event(
            draft,
            "patch_applied",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            applied_patch=applied_patch,
        )
        self.record_event(
            draft,
            "ready_for_review" if draft.ready_for_review else "validation_failed",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            applied_patch=applied_patch,
        )
        return draft

    def cancel(self, session_id: str) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft is None:
            return None
        draft.status = DraftStatus.CANCELLED
        draft.ready_for_review = False
        draft.updated_at = datetime.now(timezone.utc)
        self.record_event(draft, "draft_cancelled")
        return draft

    def clear(self, session_id: str) -> None:
        self._drafts_by_session.pop(session_id, None)

    def to_formal_intent(self, draft: TaskDraftRecord) -> dict[str, Any]:
        return self.create_proposal_intent(draft)

    def create_proposal_intent(
        self,
        draft: TaskDraftRecord,
        *,
        user_message: str | None = None,
    ) -> dict[str, Any]:
        if draft.task_type != TaskType.WEIGHING:
            raise ValueError("Only WEIGHING drafts can be converted in phase 1")
        if draft.proposal_intent is not None:
            return draft.proposal_intent
        if not draft.ready_for_review:
            raise ValueError("Draft is not ready for review")

        intent = weighing_draft_to_legacy_dispense_intent(draft)
        draft.proposal_intent = intent
        draft.status = DraftStatus.PROPOSAL_CREATED
        draft.ready_for_review = False
        draft.updated_at = datetime.now(timezone.utc)
        self.record_event(draft, "user_confirmed", user_message=user_message)
        self.record_event(draft, "proposal_created", user_message=user_message)
        return intent

    def record_event(
        self,
        draft: TaskDraftRecord,
        event_type: str,
        *,
        user_message: str | None = None,
        ai_patch: dict[str, Any] | None = None,
        applied_patch: dict[str, Any] | None = None,
    ) -> None:
        draft.events.append(
            DraftEvent(
                event_type=event_type,
                draft_id=draft.draft_id,
                session_id=draft.session_id,
                user_message=user_message,
                ai_patch=ai_patch,
                applied_patch=applied_patch,
                missing_slots=list(draft.missing_slots),
            )
        )

    def _validate_and_stamp(self, draft: TaskDraftRecord) -> TaskDraftRecord:
        if draft.task_type == TaskType.WEIGHING:
            result = validate_weighing_draft(draft.current_draft)
        elif draft.task_type == TaskType.MIXING:
            result = validate_mixing_draft(draft.current_draft)
        else:
            result = validate_dispensing_draft(draft.current_draft)

        draft.complete = result.complete
        draft.missing_slots = result.missing_slots
        draft.ready_for_review = result.ready_for_review
        draft.status = (
            DraftStatus.READY_FOR_REVIEW
            if result.ready_for_review
            else DraftStatus.COLLECTING
        )
        draft.updated_at = datetime.now(timezone.utc)
        return draft

draft_manager = DraftManager()
