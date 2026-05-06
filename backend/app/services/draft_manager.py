from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.task_draft_schema import DraftEvent, DraftStatus, TaskDraftRecord, TaskType
from app.schemas.weighing_draft_schema import WEIGHING_DRAFT_DEFAULT
from app.services.draft_store import SQLiteDraftStore
from app.services.proposal_adapter import weighing_draft_to_legacy_dispense_intent
from app.validators.dispensing_validator import validate_dispensing_draft
from app.validators.mixing_validator import validate_mixing_draft
from app.validators.weighing_validator import validate_weighing_draft


class DraftManager:
    """Task draft state manager.

    The AI only supplies a field patch. This manager owns state, merging,
    validation, and conversion to a formal backend intent proposal.
    """

    ACTIVE_STATUSES = (
        DraftStatus.COLLECTING,
        DraftStatus.NEEDS_FIELD_CONFIRMATION,
        DraftStatus.READY_FOR_REVIEW,
    )
    ASR_CRITICAL_FIELDS = {"chemical_name", "target_mass", "mass_unit", "target_vessel"}
    ASR_CONFIDENCE_THRESHOLD = 0.85

    def __init__(self, store: SQLiteDraftStore | None = None) -> None:
        self._store = store
        self._drafts_by_session: dict[str, TaskDraftRecord] = {}
        self._drafts_by_id: dict[str, TaskDraftRecord] = {}
        if self._store is not None:
            for draft in self._store.load_all():
                self._register(draft)

    def get_active(self, session_id: str) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft and draft.status in self.ACTIVE_STATUSES:
            return draft
        return None

    def get_by_draft_id(self, draft_id: str) -> TaskDraftRecord | None:
        return self._drafts_by_id.get(draft_id)

    def start(self, session_id: str, task_type: TaskType) -> TaskDraftRecord:
        if task_type != TaskType.WEIGHING:
            raise ValueError("Only WEIGHING drafts are supported in phase 1")

        draft = TaskDraftRecord(
            draft_id=f"draft_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            task_type=task_type,
            current_draft=dict(WEIGHING_DRAFT_DEFAULT),
        )
        draft = self._validate_and_stamp(draft)
        self._register(draft)
        self.record_event(draft, "draft_created")
        return draft

    def apply_patch(
        self,
        session_id: str,
        task_type: TaskType,
        patch: dict[str, Any],
        *,
        user_message: str | None = None,
        ai_patch: dict[str, Any] | None = None,
        asr: dict[str, Any] | None = None,
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
        self._apply_asr_guard(draft, applied_patch, asr)
        self.record_event(
            draft,
            "patch_applied",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            applied_patch=applied_patch,
            asr=asr,
        )
        self.record_event(
            draft,
            "ready_for_review" if draft.ready_for_review else "validation_failed",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            applied_patch=applied_patch,
            asr=asr,
        )
        return draft

    def confirm_asr_fields(
        self,
        session_id: str,
        *,
        user_message: str | None = None,
    ) -> TaskDraftRecord | None:
        draft = self.get_active(session_id)
        if draft is None or draft.status != DraftStatus.NEEDS_FIELD_CONFIRMATION:
            return draft
        draft.pending_confirmation_fields = []
        if draft.asr is not None:
            draft.asr = {**draft.asr, "needs_confirmation": False}
        draft = self._validate_and_stamp(draft)
        self.record_event(draft, "asr_fields_confirmed", user_message=user_message)
        self.record_event(
            draft,
            "ready_for_review" if draft.ready_for_review else "validation_failed",
            user_message=user_message,
        )
        return draft

    def cancel(self, session_id: str) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft is None:
            return None
        draft.status = DraftStatus.CANCELLED
        draft.ready_for_review = False
        now = datetime.now(timezone.utc)
        draft.updated_at = now
        draft.cancelled_at = now
        self.record_event(draft, "draft_cancelled")
        return draft

    def clear(self, session_id: str) -> None:
        draft = self._drafts_by_session.pop(session_id, None)
        if draft is not None and self._store is not None:
            self._store.delete(draft.draft_id)
            self._drafts_by_id.pop(draft.draft_id, None)

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
        now = datetime.now(timezone.utc)
        draft.proposal_intent = intent
        draft.status = DraftStatus.PROPOSAL_CREATED
        draft.ready_for_review = False
        draft.updated_at = now
        draft.confirmed_at = now
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
        asr: dict[str, Any] | None = None,
    ) -> None:
        draft.events.append(
            DraftEvent(
                event_type=event_type,
                draft_id=draft.draft_id,
                session_id=draft.session_id,
                user_message=user_message,
                ai_patch=ai_patch,
                applied_patch=applied_patch,
                asr_raw_text=(asr or {}).get("raw_text") if asr else None,
                asr_normalized_text=(asr or {}).get("normalized_text") if asr else None,
                asr_confidence=(asr or {}).get("confidence") if asr else None,
                asr_needs_confirmation=(asr or {}).get("needs_confirmation") if asr else None,
                missing_slots=list(draft.missing_slots),
            )
        )
        self._save(draft)

    def expire_stale(
        self,
        *,
        now: datetime | None = None,
        collecting_ttl: timedelta = timedelta(minutes=30),
        review_ttl: timedelta = timedelta(minutes=10),
    ) -> list[TaskDraftRecord]:
        now = now or datetime.now(timezone.utc)
        expired: list[TaskDraftRecord] = []
        for draft in list(self._drafts_by_id.values()):
            if draft.status == DraftStatus.COLLECTING:
                ttl = collecting_ttl
            elif draft.status in (DraftStatus.NEEDS_FIELD_CONFIRMATION, DraftStatus.READY_FOR_REVIEW):
                ttl = review_ttl
            else:
                continue
            if now - draft.updated_at <= ttl:
                continue
            draft.status = DraftStatus.EXPIRED
            draft.ready_for_review = False
            draft.updated_at = now
            self.record_event(draft, "draft_expired")
            expired.append(draft)
        return expired

    def list_drafts(self) -> list[TaskDraftRecord]:
        return list(self._drafts_by_id.values())

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

    def _apply_asr_guard(
        self,
        draft: TaskDraftRecord,
        applied_patch: dict[str, Any],
        asr: dict[str, Any] | None,
    ) -> None:
        if not asr:
            return
        critical_fields = sorted(self.ASR_CRITICAL_FIELDS.intersection(applied_patch))
        confidence = asr.get("confidence")
        low_confidence = (
            isinstance(confidence, (int, float))
            and confidence < self.ASR_CONFIDENCE_THRESHOLD
        )
        needs_confirmation = bool(asr.get("needs_confirmation")) or low_confidence
        draft.asr = {
            "raw_text": asr.get("raw_text"),
            "normalized_text": asr.get("normalized_text"),
            "confidence": confidence,
            "needs_confirmation": needs_confirmation and bool(critical_fields),
        }
        if not needs_confirmation or not critical_fields:
            return
        draft.pending_confirmation_fields = critical_fields
        draft.ready_for_review = False
        draft.status = DraftStatus.NEEDS_FIELD_CONFIRMATION

    def _register(self, draft: TaskDraftRecord) -> None:
        self._drafts_by_id[draft.draft_id] = draft
        existing = self._drafts_by_session.get(draft.session_id)
        if existing is None or existing.updated_at <= draft.updated_at:
            self._drafts_by_session[draft.session_id] = draft

    def _save(self, draft: TaskDraftRecord) -> None:
        self._register(draft)
        if self._store is not None:
            self._store.save(draft)

draft_manager = DraftManager(store=SQLiteDraftStore())
