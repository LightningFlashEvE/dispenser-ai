from __future__ import annotations

from app.schemas.task_draft_schema import DraftValidationResult


REQUIRED_WEIGHING_SLOTS = [
    "chemical_id",
    "target_mass",
    "mass_unit",
    "target_vessel",
]

VALID_MASS_UNITS = {"mg", "g", "kg", "毫克", "克", "千克"}


def validate_weighing_draft(draft: dict) -> DraftValidationResult:
    missing = [
        slot
        for slot in REQUIRED_WEIGHING_SLOTS
        if draft.get(slot) is None or draft.get(slot) == ""
    ]
    errors: list[str] = []

    catalog_status = draft.get("catalog_match_status")
    if catalog_status != "CONFIRMED":
        if "chemical_id" not in missing:
            missing.insert(0, "chemical_id")
        if catalog_status == "NO_MATCH":
            errors.append("chemical catalog lookup returned no candidates")
        elif catalog_status == "MULTIPLE_CANDIDATES":
            errors.append("chemical catalog candidate must be selected")
        elif catalog_status not in ("UNMATCHED", "SINGLE_MATCH", None):
            errors.append(f"unsupported catalog_match_status: {catalog_status}")

    target_mass = draft.get("target_mass")
    if target_mass is not None:
        try:
            if float(target_mass) <= 0:
                errors.append("target_mass must be greater than 0")
        except (TypeError, ValueError):
            errors.append("target_mass must be numeric")

    mass_unit = draft.get("mass_unit")
    if mass_unit is not None and mass_unit not in VALID_MASS_UNITS:
        errors.append(f"unsupported mass_unit: {mass_unit}")

    pending_fields = draft.get("pending_confirmation_fields") or []
    if pending_fields:
        errors.append("pending field confirmation is required")

    complete = not missing and not errors
    return DraftValidationResult(
        complete=complete,
        missing_slots=missing,
        ready_for_review=complete,
        errors=errors,
    )
