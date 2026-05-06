from __future__ import annotations

from app.schemas.task_draft_schema import DraftValidationResult


def validate_dispensing_draft(draft: dict) -> DraftValidationResult:
    missing = [
        slot
        for slot in (
            "source_material",
            "portion_count",
            "mass_per_portion",
            "mass_unit",
            "target_vessels",
            "purpose",
        )
        if draft.get(slot) in (None, "", [])
    ]
    return DraftValidationResult(
        complete=False,
        missing_slots=missing,
        ready_for_review=False,
        errors=["DISPENSING draft collection is not executable in phase 1"],
    )

