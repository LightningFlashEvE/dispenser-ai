import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

INTENT_TO_COMMAND = {
    "dispense_powder": "dispense",
    "aliquot_powder": "aliquot",
    "mix_powder": "mix",
    "query_stock": "query_stock",
    "query_device_status": "device_status",
    "save_formula": "formula",
    "restock": "restock",
    "cancel_task": "cancel",
    "emergency_stop": "emergency_stop",
}

COMMANDS_REQUIRING_CONFIRMATION = {
    "dispense", "aliquot", "mix", "formula", "restock",
}

REAGENT_FIELDS = [
    "reagent_code", "reagent_name_cn", "reagent_name_en",
    "reagent_name_formula", "purity_grade", "station_id",
    "molar_weight_g_mol",
]


def _extract_reagent_fields(drug: dict | None) -> dict:
    if not drug:
        return {}
    return {k: v for k, v in drug.items() if k in REAGENT_FIELDS and v is not None}


def _expand_mix_component(comp: dict) -> dict:
    return {
        "raw_text": comp.get("raw_text"),
        "fraction": comp.get("fraction"),
    }


async def build_command(
    intent_data: dict,
    drug_info: dict | None = None,
) -> dict[str, Any]:
    intent_type = intent_data["intent_type"]
    command_type = INTENT_TO_COMMAND.get(intent_type)

    if command_type is None:
        raise ValueError(f"未知 intent_type: {intent_type}")

    payload_builder = {
        "dispense": _build_dispense_payload,
        "aliquot": _build_aliquot_payload,
        "mix": _build_mix_payload,
        "query_stock": _build_query_stock_payload,
        "device_status": _build_device_status_payload,
        "formula": _build_formula_payload,
        "restock": _build_restock_payload,
        "cancel": _build_cancel_payload,
        "emergency_stop": _build_emergency_stop_payload,
    }

    builder = payload_builder.get(command_type)
    if not builder:
        raise ValueError(f"无对应的 payload 构建器: {command_type}")

    payload = builder(intent_data, drug_info)

    command = {
        "schema_version": "2.1",
        "command_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator_id": "admin",
        "command_type": command_type,
        "payload": payload,
    }

    if command_type in COMMANDS_REQUIRING_CONFIRMATION and not settings.skip_confirmation:
        command["confirmation"] = {
            "method": "voice",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }

    return command


def _build_dispense_payload(intent: dict, drug: dict | None) -> dict:
    params = intent.get("params", {})
    reagent = _extract_reagent_fields(drug)
    return {
        "target_mass_mg": params.get("target_mass_mg"),
        "tolerance_mg": params.get("tolerance_mg") or _calc_default_tolerance(params.get("target_mass_mg", 0)),
        "target_vessel": params.get("target_vessel"),
        **reagent,
    }


def _build_aliquot_payload(intent: dict, drug: dict | None) -> dict:
    params = intent.get("params", {})
    reagent = _extract_reagent_fields(drug)
    return {
        "portions": params.get("portions"),
        "mass_per_portion_mg": params.get("mass_per_portion_mg"),
        "tolerance_mg": params.get("tolerance_mg") or _calc_default_tolerance(params.get("mass_per_portion_mg", 0)),
        "target_vessels": params.get("target_vessels"),
        **reagent,
    }


def _build_mix_payload(intent: dict, drug: dict | None) -> dict:
    params = intent.get("params", {})
    components = params.get("components", [])
    expanded_components = [_expand_mix_component(c) for c in components]
    return {
        "total_mass_mg": params.get("total_mass_mg"),
        "ratio_type": params.get("ratio_type") or "mass_fraction",
        "components": expanded_components,
        "target_vessel": params.get("target_vessel"),
        "execution_mode": "sequential",
    }


def _build_query_stock_payload(intent: dict, drug: dict | None) -> dict:
    params = intent.get("params", {})
    return {"raw_text": params.get("raw_text")}


def _build_device_status_payload(intent: dict, drug: dict | None) -> dict:
    return {}


def _build_formula_payload(intent: dict, drug: dict | None) -> dict:
    return {}


def _build_restock_payload(intent: dict, drug: dict | None) -> dict:
    params = intent.get("params", {})
    reagent = _extract_reagent_fields(drug)
    return {
        "added_mass_mg": params.get("added_mass_mg"),
        "station_id": params.get("station_id") or reagent.get("station_id"),
        **reagent,
    }


def _build_cancel_payload(intent: dict, drug: dict | None) -> dict:
    return {}


def _build_emergency_stop_payload(intent: dict, drug: dict | None) -> dict:
    return {}


def _calc_default_tolerance(target_mass_mg: int) -> int:
    if not target_mass_mg or target_mass_mg <= 0:
        return settings.default_tolerance_mg
    pct_value = int(target_mass_mg * settings.default_tolerance_pct / 100)
    return max(settings.default_tolerance_mg, pct_value)


def load_command_schema() -> dict:
    path = Path(settings.command_schema_path).resolve()
    if not path.exists():
        logger.warning("command_schema.json 不存在: %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
