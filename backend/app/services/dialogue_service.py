from __future__ import annotations

from typing import Any

from app.schemas.task_draft_schema import TaskDraftRecord


SLOT_LABELS = {
    "chemical_name": "药品名称",
    "target_mass": "称量质量",
    "mass_unit": "单位",
    "target_vessel": "目标容器",
    "purpose": "本次任务用途",
}


def build_draft_reply(draft: TaskDraftRecord) -> str:
    if draft.ready_for_review:
        data = draft.current_draft
        return (
            "我理解为："
            f"称量 {_format_amount(data.get('target_mass'))}{data.get('mass_unit')} "
            f"{data.get('chemical_name')}，放入 {data.get('target_vessel')}，"
            f"用于{data.get('purpose')}。请确认是否正确。"
        )

    labels = [SLOT_LABELS.get(slot, slot) for slot in draft.missing_slots]
    if not labels:
        return "请继续补充本次称量任务的信息。"
    return f"请补充{_join_cn(labels)}。"


def build_cancel_reply(had_draft: bool) -> str:
    return "已取消当前任务草稿。" if had_draft else "当前没有正在收集的任务草稿。"


def build_proposal_reply(intent_data: dict[str, Any]) -> str:
    params = intent_data.get("params") or {}
    reagent = (intent_data.get("reagent_hint") or {}).get("raw_text")
    return (
        "已生成正式任务 proposal，等待规则引擎校验："
        f"称量 {params.get('target_mass_mg')}mg {reagent}，"
        f"目标容器 {params.get('target_vessel')}。"
    )


def _join_cn(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return "、".join(items[:-1]) + "和" + items[-1]


def _format_amount(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
