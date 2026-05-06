"""Intent 校验：jsonschema Draft-07 + 业务规则检查。

两层校验：
1. Schema 层：`intent_schema.json` 的 Draft-07 校验（字段类型、enum、范围等）
2. 业务层：槽位完整性、质量上限、混合比例和等业务约束

注意：INTENT_TYPES / SLOT_RULES 与 shared/intent_schema.json 保持一致。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from app.core.config import settings

logger = logging.getLogger(__name__)


INTENT_TYPES: set[str] = {
    "dispense",
    "aliquot",
    "mix",
    "formula",
    "query_stock",
    "device_status",
    "restock",
    "cancel",
    "emergency_stop",
    "unknown",
}

# 这些 intent_type 不需要槽位补全，直接通过校验
INTENT_TYPES_NO_SLOTS: set[str] = {
    "query_stock",
    "device_status",
    "formula",
    "cancel",
    "emergency_stop",
    "unknown",
}

SLOT_RULES: dict[str, dict[str, list[str]]] = {
    "dispense": {
        "required_slots": [
            "reagent_hint.raw_text",
            "params.target_mass_mg",
            "params.target_vessel",
        ],
        "optional_slots": ["params.tolerance_mg"],
    },
    "aliquot": {
        "required_slots": [
            "reagent_hint.raw_text",
            "params.portions",
            "params.mass_per_portion_mg",
        ],
        "optional_slots": ["params.tolerance_mg", "params.target_vessels"],
    },
    "mix": {
        "required_slots": ["params.total_mass_mg", "params.components"],
        "optional_slots": ["params.ratio_type", "params.target_vessel"],
    },
    "query_stock": {
        "required_slots": [],
        "optional_slots": ["reagent_hint.raw_text"],
    },
    "formula": {
        "required_slots": [],
        "optional_slots": [],
    },
    "restock": {
        "required_slots": ["reagent_hint.raw_text", "params.added_mass_mg"],
        "optional_slots": ["params.station_id"],
    },
}


# ─── Schema 层（jsonschema Draft-07） ─────────────────────────────

_schema_validator: Draft7Validator | None = None


def load_intent_schema() -> dict:
    path = Path(settings.intent_schema_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"intent_schema.json 不存在: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "properties" not in data:
        raise ValueError(f"intent_schema.json 格式无效: {path}")
    return data


def get_intent_validator() -> Draft7Validator:
    global _schema_validator
    if _schema_validator is None:
        schema = load_intent_schema()
        _schema_validator = Draft7Validator(schema)
    return _schema_validator


def validate_intent_schema(intent_data: dict) -> list[str]:
    """纯 Schema 校验，返回人类可读错误列表（空列表=通过）。"""
    validator = get_intent_validator()
    errors: list[str] = []
    for err in sorted(validator.iter_errors(intent_data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


# ─── 业务层 ───────────────────────────────────────────────────────

def _get_nested(data: dict, path: str) -> Any:
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def validate_intent(
    intent_data: dict,
    *,
    strict_schema: bool = False,
) -> tuple[bool, list[str], str | None]:
    """校验 LLM 输出的 intent_json。

    Args:
        intent_data: LLM 输出的 dict
        strict_schema: 是否启用 Draft-07 Schema 校验（默认 True）

    Returns:
        (is_valid, errors, clarification_question)
    """
    errors: list[str] = []

    if strict_schema:
        schema_errors = validate_intent_schema(intent_data)
        if schema_errors:
            return False, schema_errors, None

    intent_type = intent_data.get("intent_type")
    if intent_type not in INTENT_TYPES:
        errors.append(f"intent_type '{intent_type}' 不在允许的枚举中")
        return False, errors, None

    if intent_type in INTENT_TYPES_NO_SLOTS:
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

    params = intent_data.get("params", {}) or {}
    if intent_type == "mix":
        components = params.get("components")
        if components and isinstance(components, list):
            fractions = [
                c.get("fraction") for c in components if c.get("fraction") is not None
            ]
            if fractions and abs(sum(fractions) - 1.0) > 0.02:
                errors.append(f"组分 fraction 之和 {sum(fractions):.4f} ≠ 1.0")

    target_mass = (
        params.get("target_mass_mg")
        or params.get("mass_per_portion_mg")
        or params.get("total_mass_mg")
    )
    if target_mass is not None:
        if not isinstance(target_mass, int) or target_mass <= 0:
            errors.append(f"质量必须为正整数 mg，得到 {target_mass}")
        elif target_mass > settings.balance_max_mass_mg:
            errors.append(
                f"目标质量 {target_mass} mg 超过量程 {settings.balance_max_mass_mg} mg"
            )

    return len(errors) == 0, errors, None


__all__ = [
    "INTENT_TYPES",
    "INTENT_TYPES_NO_SLOTS",
    "SLOT_RULES",
    "validate_intent",
    "validate_intent_schema",
    "load_intent_schema",
    "get_intent_validator",
]
