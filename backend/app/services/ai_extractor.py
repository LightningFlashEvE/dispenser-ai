from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas.task_draft_schema import TaskType

logger = logging.getLogger(__name__)

ALLOWED_PATCH_FIELDS: dict[TaskType, set[str]] = {
    TaskType.WEIGHING: {
        "chemical_name",
        "target_mass",
        "mass_unit",
        "target_vessel",
    },
    TaskType.DISPENSING: {
        "source_material_text",
        "portion_count",
        "amount_per_portion",
        "amount_unit",
        "target_vessels",
    },
}

AI_EXTRACTOR_PROMPT = """\
你是配药设备的字段提取器，只能从用户本轮话语中提取字段 patch。

硬约束：
1. 只输出 JSON，格式为 {{"patch": {{...}}}}
2. 只提取用户本轮明确说出的字段，不要根据常识、历史草稿或上下文推测
3. 用户没有明确说的字段不要输出，也不要用 null 占位
4. 不判断 complete / ready_for_review / 是否可执行
5. 不生成最终 intent、proposal、command 或任何控制指令
6. 禁止输出 chemical_id、station_id、slot_id、motor_id、pump_id、valve_id、reagent_code、bottle_id
7. 禁止自动选择化学品规格、工位、槽位、电机、泵、阀门或容器实体 ID
8. 目标容器只能输出用户原话中的文本，例如 "空瓶1"、"A1"、"1号工位"

允许字段：
- WEIGHING: chemical_name, target_mass, mass_unit, target_vessel
- DISPENSING: source_material_text, portion_count, amount_per_portion, amount_unit, target_vessels

任务类型：{task_type}
当前草稿（只用于理解当前任务类型，不可用于补全字段）：{current_draft}
用户本轮输入：{user_message}
"""


class AIExtractor:
    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm
        self.last_raw_output: str | None = None
        self.last_sanitized_patch: dict[str, Any] = {}
        self.last_discarded_fields: dict[str, Any] = {}

    async def extract_patch(
        self,
        task_type: TaskType,
        current_draft: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        llm_patch: dict[str, Any] | None = None
        if self._llm is not None:
            llm_patch = await self._extract_with_llm(task_type, current_draft, user_message)
        rule_patch = _extract_with_rules(task_type, user_message)
        merged_patch = {**rule_patch, **(llm_patch or {})}
        self.last_sanitized_patch, self.last_discarded_fields = _sanitize_patch_with_discarded(task_type, merged_patch)
        return self.last_sanitized_patch

    async def _extract_with_llm(
        self,
        task_type: TaskType,
        current_draft: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any] | None:
        prompt = AI_EXTRACTOR_PROMPT.format(
            task_type=task_type.value,
            current_draft=json.dumps(current_draft, ensure_ascii=False),
            user_message=user_message,
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await self._llm._call(messages, force_json=True)
            self.last_raw_output = raw
        except Exception as e:
            logger.warning("AI extractor failed, using rule fallback: %s", e)
            self.last_raw_output = None
            return None
        parsed = _parse_json(raw)
        if not isinstance(parsed, dict):
            return None
        patch = parsed.get("patch")
        return patch if isinstance(patch, dict) else None


def _sanitize_patch(task_type: TaskType, patch: dict[str, Any]) -> dict[str, Any]:
    clean, _ = _sanitize_patch_with_discarded(task_type, patch)
    return clean


def _sanitize_patch_with_discarded(
    task_type: TaskType,
    patch: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = ALLOWED_PATCH_FIELDS.get(task_type, set())
    clean: dict[str, Any] = {}
    discarded: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in allowed:
            discarded[key] = value
            continue
        if value is None or value == "":
            continue
        if key in {"target_mass", "amount_per_portion"}:
            parsed = _parse_amount_value(value)
            if parsed is None:
                discarded[key] = value
                continue
            clean[key] = parsed[0]
            unit_key = "mass_unit" if key == "target_mass" else "amount_unit"
            if parsed[1] and unit_key in allowed:
                clean[unit_key] = _normalize_unit(parsed[1])
            continue
        if key in {"mass_unit", "amount_unit"}:
            clean[key] = _normalize_unit(str(value))
            continue
        clean[key] = value
    return clean, discarded


def _extract_with_rules(task_type: TaskType, text: str) -> dict[str, Any]:
    if task_type == TaskType.DISPENSING:
        return _extract_dispensing_with_rules(text)
    if task_type != TaskType.WEIGHING:
        return {}

    patch: dict[str, Any] = {}
    mass_match = re.search(
        r"(?:改成|改为)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg|毫克|克|千克)",
        text,
        re.I,
    )
    if not mass_match:
        mass_match = re.search(
            r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg|毫克|克|千克)",
            text,
            re.I,
        )
    if mass_match:
        patch["target_mass"] = float(mass_match.group("value"))
        patch["mass_unit"] = _normalize_unit(mass_match.group("unit"))
    else:
        mass_value_only = re.search(
            r"(?:质量|重量|称量|称重)\s*(?:改成|改为|改|为|是)?\s*(?P<value>\d+(?:\.\d+)?)",
            text,
            re.I,
        )
        if mass_value_only:
            patch["target_mass"] = float(mass_value_only.group("value"))

    # 优先匹配：放到/放入/到 + 容器标识
    vessel_match = re.search(
        r"(?:放到|放入|放|到|容器|工位)\s*(?P<vessel>(?:空瓶|试剂瓶|瓶子?)\d+|[A-Za-z]\d+|\d+号?工位)",
        text
    )
    if vessel_match:
        vessel = vessel_match.group("vessel")
        # 只对英文字母容器标识大写化，保留中文格式
        if re.match(r"^[A-Za-z]\d+$", vessel):
            patch["target_vessel"] = vessel.upper()
        else:
            patch["target_vessel"] = vessel
    else:
        # 回退：直接匹配容器标识
        simple_vessel = re.search(r"\b(?P<vessel>(?:空瓶|试剂瓶)\d+|[A-Za-z]\d+)\b", text)
        if simple_vessel:
            vessel = simple_vessel.group("vessel")
            if re.match(r"^[A-Za-z]\d+$", vessel):
                patch["target_vessel"] = vessel.upper()
            else:
                patch["target_vessel"] = vessel

    chemical = _extract_chemical_name(text)
    if chemical:
        patch["chemical_name"] = chemical

    return patch


def _parse_amount_value(value: Any) -> tuple[float, str | None] | None:
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    match = re.fullmatch(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg|毫克|克|千克)?", text, re.I)
    if not match:
        return None
    return float(match.group("value")), match.group("unit")


def _extract_dispensing_with_rules(text: str) -> dict[str, Any]:
    patch: dict[str, Any] = {}

    count_match = re.search(r"(?:分成|分)\s*(?P<count>\d+)\s*(?:份|管|瓶|个)", text)
    if not count_match:
        count_match = re.search(r"(?P<count>\d+)\s*(?:份|管|瓶|个)", text)
    if count_match:
        patch["portion_count"] = int(count_match.group("count"))

    amount_match = re.search(
        r"(?:每份|每管|每瓶|每个)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mg|g|kg|毫克|克|千克)",
        text,
        re.I,
    )
    if amount_match:
        patch["amount_per_portion"] = float(amount_match.group("value"))
        patch["amount_unit"] = _normalize_unit(amount_match.group("unit"))

    vessels = _extract_target_vessels(text)
    if vessels:
        patch["target_vessels"] = vessels

    material = _extract_source_material(text)
    if material:
        patch["source_material_text"] = material

    return patch


def _extract_target_vessels(text: str) -> list[str]:
    range_match = re.search(
        r"(?P<prefix>[A-Za-z])(?P<start>\d+)\s*[-到至]\s*(?P=prefix)?(?P<end>\d+)",
        text,
    )
    if range_match:
        prefix = range_match.group("prefix").upper()
        start = int(range_match.group("start"))
        end = int(range_match.group("end"))
        if end >= start and end - start < 100:
            return [f"{prefix}{index}" for index in range(start, end + 1)]

    vessels = re.findall(r"\b[A-Za-z]\d+\b", text)
    return [vessel.upper() for vessel in vessels]


def _extract_source_material(text: str) -> str | None:
    known = ("氯化钠", "乙醇", "无水乙醇", "葡萄糖", "碳酸氢钠", "氯化钾")
    for name in known:
        if name in text:
            return name
    match = re.search(
        r"(?:把|将|给我分|分装|分料)\s*(?P<name>[\u4e00-\u9fa5A-Za-z0-9]+?)(?:分成|分|，|,|每|$)",
        text,
    )
    if match:
        name = _clean_chemical_name(match.group("name"))
        if name:
            return name
    return None


def _normalize_unit(unit: str) -> str:
    unit_lower = unit.lower()
    if unit_lower == "mg" or unit == "毫克":
        return "mg"
    if unit_lower == "kg" or unit == "千克":
        return "kg"
    return "g"


def _extract_chemical_name(text: str) -> str | None:
    known = ("氯化钠", "乙醇", "无水乙醇", "葡萄糖", "碳酸氢钠", "氯化钾")
    for name in known:
        if name in text:
            return name
    mass_then_name = re.search(
        r"\d+(?:\.\d+)?\s*(?:mg|g|kg|毫克|克|千克)\s*(?P<name>[\u4e00-\u9fa5A-Za-z0-9]+)",
        text,
        re.I,
    )
    if mass_then_name:
        name = _clean_chemical_name(mass_then_name.group("name"))
        if name:
            return name
    match = re.search(r"(?:称取|称量|称重|称|我要|帮我)\s*(?:一点|一些)?(?P<name>[\u4e00-\u9fa5A-Za-z0-9]+)", text)
    if match:
        name = _clean_chemical_name(match.group("name"))
        if name:
            return name
    return None


def _clean_chemical_name(value: str) -> str | None:
    name = re.sub(r"^\d+(?:\.\d+)?(?:mg|g|kg|毫克|克|千克)?", "", value.strip(), flags=re.I)
    name = name.strip(" ，。,.")
    if name and name not in ("一点", "一些"):
        return name
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    value = text.strip()
    if value.startswith("```"):
        value = value.split("```", 1)[1]
        if value.startswith("json"):
            value = value[4:]
        value = value.split("```", 1)[0].strip()
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(value[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None
