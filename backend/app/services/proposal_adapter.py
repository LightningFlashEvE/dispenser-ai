from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.task_draft_schema import TaskDraftRecord, TaskType


def weighing_draft_to_legacy_dispense_intent(draft: TaskDraftRecord) -> dict[str, Any]:
    """Adapt WEIGHING draft data to the current rule engine's dispense intent."""
    if draft.task_type != TaskType.WEIGHING:
        raise ValueError("Only WEIGHING drafts can be adapted in phase 1")

    data = draft.current_draft
    return {
        "schema_version": "1.0",
        "intent_id": f"intent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "intent_type": "dispense",
        "task_type": draft.task_type.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_complete": True,
        "missing_slots": [],
        "clarification_question": None,
        "reagent_hint": {
            "raw_text": data["chemical_name"],
            "guessed_code": None,
            "guessed_name_cn": data["chemical_name"],
            "guessed_name_formula": None,
        },
        "params": {
            "target_mass_mg": mass_to_mg(data["target_mass"], data["mass_unit"]),
            "tolerance_mg": None,
            "target_vessel": data["target_vessel"],
        },
        "raw_asr_text": draft_summary(data),
        "confidence": 1.0,
        "draft_id": draft.draft_id,
        "purpose": data.get("purpose"),
    }


def mass_to_mg(value: Any, unit: Any) -> int:
    amount = float(value)
    unit_text = str(unit)
    if unit_text in ("g", "克"):
        return int(round(amount * 1000))
    if unit_text in ("kg", "千克"):
        return int(round(amount * 1000 * 1000))
    return int(round(amount))


def draft_summary(data: dict[str, Any]) -> str:
    return (
        f"称量 {data.get('target_mass')}{data.get('mass_unit')} "
        f"{data.get('chemical_name')} 到 {data.get('target_vessel')}，"
        f"用途：{data.get('purpose')}"
    )

