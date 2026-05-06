from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.schemas.task_draft_schema import TaskDraftRecord, TaskType


Route = Literal[
    "normal_chat",
    "query_inventory",
    "query_formula",
    "query_device_status",
    "start_task",
    "update_task",
    "cancel_task",
    "confirm_task",
    "clarify",
]


@dataclass(frozen=True)
class RouteResult:
    route: Route
    task_type: TaskType | None = None
    clarification: str | None = None
    query_keyword: str | None = None


CONFIRM_WORDS = ("确认", "是的", "对", "没错", "执行", "开始")
CANCEL_WORDS = ("取消", "不要了", "重来", "清空", "算了")
WEIGHING_WORDS = ("称", "称量", "称取", "称重")
DISPENSING_WORDS = ("分装", "分料", "分成", "每管", "每份")
MIXING_WORDS = ("混合", "配制", "配 ", "配方", "溶液", "%")

_QUERY_PREFIX_RE = re.compile(r"^(查一下|查下|查询|查查|查|帮我查|帮我|看看|找|搜|有没有)\s*")
_QUERY_SUFFIX_RE = re.compile(r"\s*(的|了|库存|还有多少|剩多少|还有吗|有吗|在哪|在哪?个工位|位置|量|情况|信息)+$")


def route_intent(user_text: str, active_draft: TaskDraftRecord | None = None) -> RouteResult:
    text = user_text.strip()
    if not text:
        return RouteResult(route="normal_chat")

    if _contains_any(text, CANCEL_WORDS):
        return RouteResult(route="cancel_task")

    if _contains_any(text, CONFIRM_WORDS):
        if active_draft and active_draft.ready_for_review:
            return RouteResult(route="confirm_task", task_type=active_draft.task_type)
        if active_draft:
            return RouteResult(
                route="clarify",
                task_type=active_draft.task_type,
                clarification="当前信息还不完整，请先补充缺失字段。",
            )

    if re.search(r"(查询|查一下|查查|帮我查|库存|还有多少|剩多少|有没有|在哪|工位)", text):
        kw = _extract_drug_keyword(text)
        return RouteResult(route="query_inventory", query_keyword=kw)

    if re.search(r"(查看|查询|看一下|看下|列出|显示).*(配方|配方列表)", text) or re.fullmatch(r"(配方|配方列表|所有配方|全部配方|查看配方|查询配方)", text):
        return RouteResult(route="query_formula")

    if re.search(r"(设备状态|天平状态|状态)", text):
        return RouteResult(route="query_device_status")

    if active_draft and active_draft.status.value in ("COLLECTING", "READY_FOR_REVIEW"):
        return RouteResult(route="update_task", task_type=active_draft.task_type)

    has_weighing = _contains_any(text, WEIGHING_WORDS)
    has_dispensing = _contains_any(text, DISPENSING_WORDS)
    has_mixing = _contains_any(text, MIXING_WORDS)

    if has_weighing and not has_dispensing and not has_mixing:
        return RouteResult(route="start_task", task_type=TaskType.WEIGHING)

    if has_dispensing and not has_weighing and not has_mixing:
        return RouteResult(
            route="clarify",
            task_type=TaskType.DISPENSING,
            clarification="分料任务将在第二阶段开放；当前请先使用称量任务。",
        )

    if has_mixing and not has_weighing and not has_dispensing:
        return RouteResult(
            route="clarify",
            task_type=TaskType.MIXING,
            clarification="混合任务涉及配方和审批，第一阶段先只收集称量任务。",
        )

    if _looks_like_task_seed(text):
        return RouteResult(
            route="clarify",
            clarification="请确认你要进行称量、混合，还是分料？",
        )

    return RouteResult(route="normal_chat")


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _extract_drug_keyword(text: str) -> str:
    """从库存查询文本中剥离查询功能词，提取可能的药品名。"""
    t = _QUERY_PREFIX_RE.sub("", text.strip())
    t = _QUERY_SUFFIX_RE.sub("", t)
    return t.strip() or text.strip()


def _looks_like_task_seed(text: str) -> bool:
    return bool(re.search(r"(我要|帮我|来点|一点|乙醇|氯化钠|葡萄糖|毫克|克|mg|g)", text, re.I))

