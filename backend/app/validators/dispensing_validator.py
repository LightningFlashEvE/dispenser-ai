from __future__ import annotations

from app.schemas.task_draft_schema import DraftValidationResult

VALID_AMOUNT_UNITS = {"mg", "g", "kg", "毫克", "克", "千克"}


def validate_dispensing_draft(draft: dict) -> DraftValidationResult:
    missing = [
        slot
        for slot in (
            "chemical_id",
            "portion_count",
            "amount_per_portion",
            "amount_unit",
            "target_vessels",
            "purpose",
        )
        if draft.get(slot) in (None, "", [])
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

    portion_count = draft.get("portion_count")
    if portion_count is not None:
        try:
            if int(portion_count) <= 0:
                errors.append("portion_count must be greater than 0")
        except (TypeError, ValueError):
            errors.append("portion_count must be an integer")

    amount = draft.get("amount_per_portion")
    if amount is not None:
        try:
            if float(amount) <= 0:
                errors.append("amount_per_portion must be greater than 0")
        except (TypeError, ValueError):
            errors.append("amount_per_portion must be numeric")

    amount_unit = draft.get("amount_unit")
    if amount_unit is not None and amount_unit not in VALID_AMOUNT_UNITS:
        errors.append(f"unsupported amount_unit: {amount_unit}")

    target_vessels = draft.get("target_vessels")
    if target_vessels not in (None, ""):
        if not isinstance(target_vessels, list):
            errors.append("target_vessels must be a list")
        elif portion_count is not None and len(target_vessels) != int(portion_count):
            errors.append("target_vessels count must equal portion_count")

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
