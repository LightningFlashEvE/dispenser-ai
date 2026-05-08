from __future__ import annotations

from typing import Any

from app.schemas.task_draft_schema import DraftStatus, TaskDraftRecord


SLOT_LABELS = {
    "chemical_name": "药品名称",
    "chemical_id": "化学品 catalog 确认",
    "catalog_candidate": "具体化学品候选",
    "source_material_text": "来源物料",
    "target_mass": "称量质量",
    "mass_unit": "单位",
    "portion_count": "分料份数",
    "amount_per_portion": "每份数量",
    "amount_unit": "单位",
    "target_vessels": "目标容器",
    "target_vessel": "目标容器",
}


def build_draft_reply(draft: TaskDraftRecord) -> str:
    if draft.status == DraftStatus.NEEDS_FIELD_CONFIRMATION:
        data = draft.current_draft
        if "catalog_candidate" in draft.pending_confirmation_fields:
            candidates = data.get("catalog_candidates") or []
            if data.get("catalog_match_status") == "NO_MATCH":
                return f"未找到化学品：{data.get('chemical_name_text') or '未知'}。请重新说明化学品名称。"
            lines = [
                f"检测到多个化学品候选，请选择具体化学品：",
            ]
            for index, candidate in enumerate(candidates, start=1):
                lines.append(
                    f"{index}. {candidate.get('display_name')} "
                    f"{candidate.get('grade') or ''} "
                    f"CAS {candidate.get('cas_no') or '未知'} "
                    f"({candidate.get('chemical_id')})"
                )
            return "\n".join(lines)

        asr = draft.asr or {}
        parts: list[str] = []
        if draft.task_type.value == "DISPENSING":
            if data.get("portion_count"):
                parts.append(f"分成 {data.get('portion_count')} 份")
            if data.get("amount_per_portion") and data.get("amount_unit"):
                parts.append(f"每份 {data.get('amount_per_portion')}{data.get('amount_unit')}")
            if data.get("source_material_text"):
                parts.append(str(data.get("source_material_text")))
        elif data.get("target_mass") and data.get("mass_unit"):
            parts.append(f"称量 {_format_amount(data.get('target_mass'))}{data.get('mass_unit')}")
        if data.get("chemical_name"):
            parts.append(str(data.get("chemical_name")))
        if data.get("target_vessel"):
            parts.append(f"放入 {data.get('target_vessel')}")
        summary = " ".join(parts) if parts else "更新称量任务信息"
        return (
            f"识别到你可能要{summary}。"
            f"原始识别：{asr.get('raw_text') or '未知'}。"
            "请先确认语音识别内容是否正确。"
        )

    if draft.ready_for_review:
        data = draft.current_draft
        catalog = ""
        if data.get("chemical_id"):
            catalog = (
                f"系统匹配：{data.get('chemical_display_name')} / "
                f"{data.get('grade') or '未标注等级'} / "
                f"CAS {data.get('cas_no') or '未知'}。"
            )
        if draft.task_type.value == "DISPENSING":
            return (
                "我理解为："
                f"将 {data.get('chemical_display_name') or data.get('source_material_text')} "
                f"分成 {data.get('portion_count')} 份，"
                f"每份 {_format_amount(data.get('amount_per_portion'))}{data.get('amount_unit')}，"
                f"放入 {', '.join(data.get('target_vessels') or [])}。"
                f"{catalog}请确认是否正确。"
            )
        return (
            "我理解为："
            f"称量 {_format_amount(data.get('target_mass'))}{data.get('mass_unit')} "
            f"{data.get('chemical_display_name') or data.get('chemical_name')}，"
            f"放入 {data.get('target_vessel')}。"
            f"{catalog}请确认是否正确。"
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
    if intent_data.get("task_type") == "DISPENSING":
        return (
            "已生成正式任务 proposal，等待规则引擎校验："
            f"分料 {params.get('portions')} 份 {reagent}，"
            f"每份 {params.get('mass_per_portion_mg')}mg，"
            f"目标容器 {', '.join(params.get('target_vessels') or [])}。"
        )
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
