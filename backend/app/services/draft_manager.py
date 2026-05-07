from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.task_draft_schema import DraftEvent, DraftStatus, TaskDraftRecord, TaskType
from app.schemas.weighing_draft_schema import WEIGHING_DRAFT_DEFAULT
from app.services.chemical_catalog import (
    HIGH_CONFIDENCE_THRESHOLD,
    lookup_chemical_candidates,
    select_candidate_by_id,
    select_candidate_by_index,
)
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
    ASR_CRITICAL_FIELDS = {"chemical_name_text", "target_mass", "mass_unit", "target_vessel"}
    CATALOG_PENDING_FIELDS = ("catalog_candidate", "chemical_id")
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
        raw_ai_extractor_output: str | None = None,
        sanitized_patch: dict[str, Any] | None = None,
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
            if key in {"chemical_id", "chemical_display_name", "cas_no", "grade", "catalog_match_status", "catalog_candidates"}:
                continue
            if value is None or value == "":
                continue
            if key == "chemical_name":
                key = "chemical_name_text"
            if key in draft.current_draft:
                draft.current_draft[key] = value
                if key == "chemical_name_text":
                    draft.current_draft["chemical_name"] = value
                applied_patch[key] = value

        if "chemical_name_text" in applied_patch:
            self._lookup_catalog(draft, user_message=user_message)

        draft = self._validate_and_stamp(draft)
        self._apply_asr_guard(draft, applied_patch, asr)
        self.record_event(
            draft,
            "patch_applied",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            raw_ai_extractor_output=raw_ai_extractor_output,
            sanitized_patch=sanitized_patch if sanitized_patch is not None else patch,
            applied_patch=applied_patch,
            asr=asr,
        )
        self.record_event(
            draft,
            "ready_for_review" if draft.ready_for_review else "validation_failed",
            user_message=user_message,
            ai_patch=ai_patch if ai_patch is not None else patch,
            raw_ai_extractor_output=raw_ai_extractor_output,
            sanitized_patch=sanitized_patch if sanitized_patch is not None else patch,
            applied_patch=applied_patch,
            asr=asr,
        )
        return draft

    def confirm_catalog_candidate(
        self,
        session_id: str,
        *,
        index: int | None = None,
        chemical_id: str | None = None,
        user_message: str | None = None,
        selected_by: str = "user",
    ) -> TaskDraftRecord | None:
        draft = self.get_active(session_id)
        if draft is None:
            return None
        candidates = draft.current_draft.get("catalog_candidates") or []
        selected = None
        if chemical_id:
            selected = select_candidate_by_id(candidates, chemical_id)
        elif index is not None:
            selected = select_candidate_by_index(candidates, index)
        if selected is None:
            self.record_event(
                draft,
                "catalog_candidate_selection_failed",
                user_message=user_message,
                applied_patch={
                    "chemical_id": chemical_id,
                    "index": index,
                    "candidate_count": len(candidates),
                },
            )
            return draft

        self._apply_catalog_candidate(draft, selected, status="CONFIRMED")
        draft.pending_confirmation_fields = [
            field
            for field in draft.pending_confirmation_fields
            if field not in self.CATALOG_PENDING_FIELDS
        ]
        draft = self._validate_and_stamp(draft)
        self.record_event(
            draft,
            "catalog_candidate_confirmed",
            user_message=user_message,
            applied_patch={
                "selected_chemical_id": selected.get("chemical_id"),
                "selected_by": selected_by,
            },
        )
        self.record_event(
            draft,
            "ready_for_review" if draft.ready_for_review else "validation_failed",
            user_message=user_message,
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

    def mark_dispatched(
        self,
        session_id: str,
        *,
        command_id: str | None = None,
    ) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft is None:
            return None
        draft.status = DraftStatus.DISPATCHED
        draft.ready_for_review = False
        draft.updated_at = datetime.now(timezone.utc)
        self.record_event(
            draft,
            "command_dispatched",
            applied_patch={"command_id": command_id} if command_id else None,
        )
        return draft

    def mark_failed(
        self,
        session_id: str,
        *,
        error_message: str | None = None,
    ) -> TaskDraftRecord | None:
        draft = self._drafts_by_session.get(session_id)
        if draft is None:
            return None
        draft.status = DraftStatus.FAILED
        draft.ready_for_review = False
        draft.updated_at = datetime.now(timezone.utc)
        self.record_event(
            draft,
            "rule_check_failed",
            applied_patch={"error_message": error_message} if error_message else None,
        )
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
        raw_ai_extractor_output: str | None = None,
        sanitized_patch: dict[str, Any] | None = None,
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
                raw_ai_extractor_output=raw_ai_extractor_output,
                sanitized_patch=sanitized_patch,
                applied_patch=applied_patch,
                asr_raw_text=(asr or {}).get("raw_text") if asr else None,
                asr_normalized_text=(asr or {}).get("normalized_text") if asr else None,
                asr_confidence=(asr or {}).get("confidence") if asr else None,
                asr_needs_confirmation=(asr or {}).get("needs_confirmation") if asr else None,
                missing_slots=list(draft.missing_slots),
            )
        )
        self._save(draft)

    def _lookup_catalog(
        self,
        draft: TaskDraftRecord,
        *,
        user_message: str | None = None,
    ) -> None:
        name_text = draft.current_draft.get("chemical_name_text")
        self.record_event(
            draft,
            "catalog_lookup_started",
            user_message=user_message,
            applied_patch={"chemical_name_text": name_text},
        )
        candidates = [
            candidate.to_dict()
            for candidate in lookup_chemical_candidates(name_text)
        ]
        draft.current_draft["catalog_candidates"] = candidates
        if not candidates:
            draft.current_draft["chemical_id"] = None
            draft.current_draft["chemical_display_name"] = None
            draft.current_draft["cas_no"] = None
            draft.current_draft["grade"] = None
            draft.current_draft["catalog_match_status"] = "NO_MATCH"
            self._ensure_pending_catalog_confirmation(draft)
            self.record_event(
                draft,
                "catalog_lookup_no_match",
                user_message=user_message,
                applied_patch={
                    "chemical_name_text": name_text,
                    "candidate_count": 0,
                    "candidates": [],
                },
            )
            return

        if len(candidates) == 1 and candidates[0].get("confidence", 0) >= HIGH_CONFIDENCE_THRESHOLD:
            self._apply_catalog_candidate(draft, candidates[0], status="CONFIRMED")
            self._clear_pending_catalog_confirmation(draft)
            self.record_event(
                draft,
                "catalog_lookup_single_candidate",
                user_message=user_message,
                applied_patch={
                    "chemical_name_text": name_text,
                    "candidate_count": 1,
                    "candidates": candidates,
                    "selected_chemical_id": candidates[0].get("chemical_id"),
                    "selected_by": "catalog_lookup",
                },
            )
            return

        draft.current_draft["chemical_id"] = None
        draft.current_draft["chemical_display_name"] = None
        draft.current_draft["cas_no"] = None
        draft.current_draft["grade"] = None
        draft.current_draft["catalog_match_status"] = "MULTIPLE_CANDIDATES"
        self._ensure_pending_catalog_confirmation(draft)
        self.record_event(
            draft,
            "catalog_lookup_multiple_candidates",
            user_message=user_message,
            applied_patch={
                "chemical_name_text": name_text,
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
        )

    def _apply_catalog_candidate(
        self,
        draft: TaskDraftRecord,
        candidate: dict,
        *,
        status: str,
    ) -> None:
        draft.current_draft["chemical_id"] = candidate.get("chemical_id")
        draft.current_draft["chemical_display_name"] = candidate.get("display_name")
        draft.current_draft["chemical_name"] = candidate.get("display_name")
        draft.current_draft["cas_no"] = candidate.get("cas_no")
        draft.current_draft["grade"] = candidate.get("grade")
        draft.current_draft["catalog_match_status"] = status

    def _ensure_pending_catalog_confirmation(self, draft: TaskDraftRecord) -> None:
        existing = list(draft.pending_confirmation_fields)
        for field in self.CATALOG_PENDING_FIELDS:
            if field not in existing:
                existing.append(field)
        draft.pending_confirmation_fields = existing

    def _clear_pending_catalog_confirmation(self, draft: TaskDraftRecord) -> None:
        draft.pending_confirmation_fields = [
            field
            for field in draft.pending_confirmation_fields
            if field not in self.CATALOG_PENDING_FIELDS
        ]

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
        if draft.pending_confirmation_fields:
            draft.ready_for_review = False
            draft.status = DraftStatus.NEEDS_FIELD_CONFIRMATION
        else:
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
