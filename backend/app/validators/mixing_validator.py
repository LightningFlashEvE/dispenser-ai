from __future__ import annotations

from app.schemas.task_draft_schema import DraftValidationResult


def validate_mixing_draft(draft: dict) -> DraftValidationResult:
    missing = [
        slot
        for slot in (
            "target_product",
            "total_mass",
            "mass_unit",
            "components",
            "ratio_type",
            "target_vessel",
            "purpose",
        )
        if draft.get(slot) in (None, "", [])
    ]
    return DraftValidationResult(
        complete=False,
        missing_slots=missing,
        ready_for_review=False,
        errors=["MIXING draft collection is not executable in phase 1"],
    )

