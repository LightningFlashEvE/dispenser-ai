import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

INTENT_TYPES = {
    "dispense_powder",
    "aliquot_powder",
    "mix_powder",
    "query_stock",
    "query_device_status",
    "save_formula",
    "cancel_task",
    "emergency_stop",
    "unknown",
}

SLOT_RULES = {
    "dispense_powder": {
        "required_slots": ["reagent_hint.raw_text", "params.target_mass_mg", "params.target_vessel"],
        "optional_slots": ["params.tolerance_mg"],
    },
    "aliquot_powder": {
        "required_slots": ["reagent_hint.raw_text", "params.portions", "params.mass_per_portion_mg"],
        "optional_slots": ["params.tolerance_mg", "params.target_vessels"],
    },
    "mix_powder": {
        "required_slots": ["params.total_mass_mg", "params.components"],
        "optional_slots": ["params.ratio_type", "params.target_vessel"],
    },
    "query_stock": {
        "required_slots": [],
        "optional_slots": ["reagent_hint.raw_text"],
    },
}


def _get_nested(data: dict, path: str) -> any:
    parts = path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def validate_intent(intent_data: dict) -> tuple[bool, list[str], str | None]:
    """校验 LLM 输出的 intent_json 结构。

    Returns:
        (is_valid, errors, clarification_question)
    """
    errors: list[str] = []

    intent_type = intent_data.get("intent_type")
    if intent_type not in INTENT_TYPES:
        errors.append(f"intent_type '{intent_type}' 不在允许的枚举中")
        return False, errors, None

    if intent_type in ("query_stock", "query_device_status", "cancel_task", "emergency_stop", "unknown"):
        return True, [], None

    rules = SLOT_RULES.get(intent_type)
    if not rules:
        errors.append(f"intent_type '{intent_type}' 无对应的槽位规则")
        return False, errors, None

    is_complete = intent_data.get("is_complete", True)
    clarification = intent_data.get("clarification_question")

    if not is_complete:
        missing = intent_data.get("missing_slots", [])
        if not missing and clarification:
            errors.append("is_complete=false 但 missing_slots 为空")
        return True, [], clarification

    for slot in rules["required_slots"]:
        value = _get_nested(intent_data, slot)
        if value is None:
            errors.append(f"必填槽位 {slot} 为空")

    params = intent_data.get("params", {})
    if intent_type == "mix_powder":
        components = params.get("components")
        if components and isinstance(components, list):
            fractions = [
                c.get("fraction") for c in components if c.get("fraction") is not None
            ]
            if fractions and abs(sum(fractions) - 1.0) > 0.01:
                errors.append(f"组分 fraction 之和 {sum(fractions):.4f} ≠ 1.0")

    target_mass = params.get("target_mass_mg") or params.get("mass_per_portion_mg") or params.get("total_mass_mg")
    if target_mass is not None:
        if not isinstance(target_mass, int) or target_mass <= 0:
            errors.append(f"质量必须为正整数 mg，得到 {target_mass}")
        elif target_mass > settings.balance_max_mass_mg:
            errors.append(f"目标质量 {target_mass} mg 超过量程 {settings.balance_max_mass_mg} mg")

    return len(errors) == 0, errors, None


def load_intent_schema() -> dict:
    path = Path(settings.intent_schema_path).resolve()
    if not path.exists():
        logger.warning("intent_schema.json 不存在: %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
