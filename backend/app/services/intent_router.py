from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from app.schemas.task_draft_schema import TaskDraftRecord, TaskType


logger = logging.getLogger(__name__)

Route = Literal[
    "normal_chat",
    "query_inventory",
    "query_bottles",
    "query_formula",
    "select_formula",
    "select_catalog_candidate",
    "query_device_status",
    "start_task",
    "update_task",
    "cancel_task",
    "confirm_task",
    "confirm_fields",
    "clarify",
]


@dataclass(frozen=True)
class RouteResult:
    route: Route
    task_type: TaskType | None = None
    confidence: float = 0.0
    reason: str | None = None
    signals: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    clarification: str | None = None
    query_keyword: str | None = None
    use_llm_fallback: bool = False


CONFIRM_WORDS = ("确认", "是的", "对", "没错", "执行", "开始")
CANCEL_WORDS = ("取消", "不要了", "重来", "清空", "算了")
WEIGHING_WORDS = ("称", "称量", "称取", "称重")
DISPENSING_WORDS = ("分装", "分料", "分成", "每管", "每份", "每瓶", "aliquot")
MIXING_WORDS = ("混合", "配制", "配 ", "溶液", "%")
FORMULA_SELECT_WORDS = ("应用", "使用", "执行", "套用", "选择", "选用", "采用")

_QUERY_PREFIX_RE = re.compile(r"^(查一下|查下|查询|查查|查|帮我查|帮我|看看|找|搜|有没有)\s*")
_QUERY_SUFFIX_RE = re.compile(r"\s*(的|了|库存|还有多少|剩多少|还有吗|有吗|在哪|在哪?个工位|位置|量|情况|信息)+$")

LLM_ROUTER_PROMPT = """\
你是配药设备的意图路由兜底分类器。规则路由已经先运行，只有低置信、冲突或上下文不足时才会调用你。

硬约束：
1. 只输出 JSON，不要输出解释文本
2. 只能选择固定枚举 route：start_task、update_task、query_bottles、query_inventory、clarify、normal_chat
3. task_type 只能是 WEIGHING、DISPENSING、MIXING 或 null
4. 不生成 command、intent、proposal 或任何执行参数
5. 不判断任务是否完整，不判断是否 ready_for_review
6. 只做路由分类；字段提取由 AIExtractor 负责

强规则：
- 称/称量/称取/称重 优先判断为 start_task + WEIGHING
- 分装/分料/每份/每管 优先判断为 start_task + DISPENSING
- “空瓶1”如果出现在称量/分装语句中，是目标容器文本，不是 query_bottles
- 只有对象没有动作，或表达多义，返回 clarify

输出格式：
{{
  "route": "start_task | update_task | query_bottles | query_inventory | clarify | normal_chat",
  "task_type": "WEIGHING | DISPENSING | MIXING | null",
  "confidence": 0.0,
  "reason": ""
}}

用户输入：{user_text}
是否有 active draft：{has_active_draft}
active draft 任务类型：{active_task_type}
规则路由结果：{rule_result}
"""

LLM_ALLOWED_ROUTES: set[Route] = {
    "start_task",
    "update_task",
    "query_bottles",
    "query_inventory",
    "clarify",
    "normal_chat",
}


def route_intent(user_text: str, active_draft: TaskDraftRecord | None = None) -> RouteResult:
    text = user_text.strip()
    if not text:
        return RouteResult(route="normal_chat", confidence=1.0)

    # 检测信号和冲突
    signals = _detect_signals(text)
    conflicts = _detect_conflicts(text, signals)

    # 强规则：取消优先
    if _contains_any(text, CANCEL_WORDS):
        confidence = _calculate_confidence("cancel_task", None, signals, conflicts, active_draft)
        return RouteResult(
            route="cancel_task",
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到取消词",
        )

    # 配方查询
    if _is_formula_query(text):
        confidence = _calculate_confidence("query_formula", None, signals, conflicts, active_draft)
        return RouteResult(
            route="query_formula",
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到配方查询",
        )

    # 配方选择
    if _is_formula_selection(text):
        confidence = _calculate_confidence("select_formula", None, signals, conflicts, active_draft)
        return RouteResult(
            route="select_formula",
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到配方选择",
        )

    # 瓶子查询（任务动作优先）
    if _is_bottle_query(text):
        confidence = _calculate_confidence("query_bottles", None, signals, conflicts, active_draft)
        return RouteResult(
            route="query_bottles",
            query_keyword=text,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到瓶子查询",
        )

    # Catalog 候选选择
    if active_draft and _needs_catalog_candidate(active_draft) and _is_catalog_selection(text):
        confidence = _calculate_confidence("select_catalog_candidate", active_draft.task_type, signals, conflicts, active_draft)
        return RouteResult(
            route="select_catalog_candidate",
            task_type=active_draft.task_type,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到 catalog 候选选择",
        )

    # 确认词处理
    if _contains_any(text, CONFIRM_WORDS):
        if active_draft and active_draft.status.value == "NEEDS_FIELD_CONFIRMATION":
            confidence = _calculate_confidence("confirm_fields", active_draft.task_type, signals, conflicts, active_draft)
            return RouteResult(
                route="confirm_fields",
                task_type=active_draft.task_type,
                confidence=confidence,
                signals=tuple(signals),
                conflicts=tuple(conflicts),
                reason="确认字段",
            )
        if active_draft and active_draft.ready_for_review:
            confidence = _calculate_confidence("confirm_task", active_draft.task_type, signals, conflicts, active_draft)
            return RouteResult(
                route="confirm_task",
                task_type=active_draft.task_type,
                confidence=confidence,
                signals=tuple(signals),
                conflicts=tuple(conflicts),
                reason="确认任务",
            )
        if active_draft:
            return RouteResult(
                route="clarify",
                task_type=active_draft.task_type,
                clarification="当前信息还不完整，请先补充缺失字段。",
                confidence=0.40,
                signals=tuple(signals),
                conflicts=tuple(conflicts),
                reason="确认词但任务未就绪",
            )

    # 库存查询
    if re.search(r"(查询|查一下|查查|帮我查|库存|还有多少|剩多少|有没有|在哪|工位)", text):
        kw = _extract_drug_keyword(text)
        confidence = _calculate_confidence("query_inventory", None, signals, conflicts, active_draft)
        return RouteResult(
            route="query_inventory",
            query_keyword=kw,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到库存查询",
        )

    # 设备状态查询
    if re.search(r"(设备状态|天平状态|状态)", text):
        confidence = _calculate_confidence("query_device_status", None, signals, conflicts, active_draft)
        return RouteResult(
            route="query_device_status",
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="检测到设备状态查询",
        )

    # Active draft 更新
    if active_draft and active_draft.status.value in (
        "COLLECTING",
        "NEEDS_FIELD_CONFIRMATION",
        "READY_FOR_REVIEW",
    ):
        confidence = _calculate_confidence("update_task", active_draft.task_type, signals, conflicts, active_draft)
        return RouteResult(
            route="update_task",
            task_type=active_draft.task_type,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="active draft 存在，更新任务",
        )

    # 任务动作检测（强优先级）
    has_weighing = _contains_any(text, WEIGHING_WORDS)
    has_dispensing = _contains_any(text, DISPENSING_WORDS)
    has_mixing = _contains_any(text, MIXING_WORDS)

    if has_weighing and not has_dispensing and not has_mixing:
        confidence = _calculate_confidence("start_task", TaskType.WEIGHING, signals, conflicts, active_draft)
        return RouteResult(
            route="start_task",
            task_type=TaskType.WEIGHING,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="明确称量动作",
        )

    if has_dispensing and not has_weighing and not has_mixing:
        confidence = _calculate_confidence("start_task", TaskType.DISPENSING, signals, conflicts, active_draft)
        return RouteResult(
            route="start_task",
            task_type=TaskType.DISPENSING,
            confidence=confidence,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="明确分装动作",
        )

    # 多义表达
    if "配" in text and re.search(r"\d+\s*(管|瓶|份|个)", text):
        return RouteResult(
            route="clarify",
            clarification="你是要配制新的溶液，还是把已有物料分装成多份？",
            confidence=0.40,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="多义表达",
        )

    if has_mixing and not has_weighing and not has_dispensing:
        return RouteResult(
            route="clarify",
            task_type=TaskType.MIXING,
            clarification="混合任务涉及配方和审批，第一阶段先只收集称量任务。",
            confidence=0.40,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="混合任务暂不支持",
        )

    if _looks_like_task_seed(text):
        return RouteResult(
            route="clarify",
            clarification="请确认你要进行称量、混合，还是分料？",
            confidence=0.35,
            signals=tuple(signals),
            conflicts=tuple(conflicts),
            reason="任务种子但动作不明确",
        )

    return RouteResult(
        route="normal_chat",
        confidence=0.60,
        signals=tuple(signals),
        conflicts=tuple(conflicts),
        reason="无明确意图，默认聊天",
    )


async def route_intent_with_llm_fallback(
    user_text: str,
    active_draft: TaskDraftRecord | None = None,
    llm: Any | None = None,
) -> RouteResult:
    rule_result = route_intent(user_text, active_draft)
    if llm is None or not _should_use_llm_fallback(rule_result):
        return rule_result

    llm_result = await _route_with_llm(user_text, active_draft, rule_result, llm)
    return llm_result or rule_result


def _should_use_llm_fallback(result: RouteResult) -> bool:
    if result.confidence < 0.60:
        return True
    if result.use_llm_fallback:
        return True
    if "multiple_task_actions" in result.conflicts:
        return True
    if result.route == "clarify" and result.reason in {"多义表达", "任务种子但动作不明确"}:
        return True
    return False


async def _route_with_llm(
    user_text: str,
    active_draft: TaskDraftRecord | None,
    rule_result: RouteResult,
    llm: Any,
) -> RouteResult | None:
    prompt = LLM_ROUTER_PROMPT.format(
        user_text=user_text,
        has_active_draft=active_draft is not None,
        active_task_type=active_draft.task_type.value if active_draft else None,
        rule_result=json.dumps(_route_result_to_json(rule_result), ensure_ascii=False),
    )
    try:
        raw = await llm._call([{"role": "user", "content": prompt}], force_json=True)
    except Exception as exc:
        logger.warning("LLM router fallback failed: %s", exc)
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("LLM router fallback returned invalid JSON: %s", raw)
        return None
    if not isinstance(parsed, dict):
        return None

    route = parsed.get("route")
    if route not in LLM_ALLOWED_ROUTES:
        return None

    task_type = _parse_llm_task_type(parsed.get("task_type"))
    if route in {"start_task", "update_task"} and task_type is None:
        if active_draft and route == "update_task":
            task_type = active_draft.task_type
        else:
            route = "clarify"

    confidence = parsed.get("confidence")
    if not isinstance(confidence, int | float):
        confidence = 0.60
    confidence = max(0.0, min(1.0, float(confidence)))

    return RouteResult(
        route=route,
        task_type=task_type,
        confidence=confidence,
        reason=str(parsed.get("reason") or "LLM router fallback"),
        signals=rule_result.signals,
        conflicts=rule_result.conflicts,
        clarification="请再明确一下你要做的是称量、分装、查询，还是普通提问？" if route == "clarify" else None,
        query_keyword=user_text if route in {"query_bottles", "query_inventory"} else None,
    )


def _route_result_to_json(result: RouteResult) -> dict[str, Any]:
    return {
        "route": result.route,
        "task_type": result.task_type.value if result.task_type else None,
        "confidence": result.confidence,
        "reason": result.reason,
        "signals": list(result.signals),
        "conflicts": list(result.conflicts),
    }


def _parse_llm_task_type(value: Any) -> TaskType | None:
    if value in (None, "", "null"):
        return None
    try:
        return TaskType(str(value))
    except ValueError:
        return None


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_formula_query(text: str) -> bool:
    return bool(
        re.search(r"(查看|查询|看一下|看下|列出|显示).*(配方|配方列表)", text)
        or re.fullmatch(r"(配方|配方列表|所有配方|全部配方|查看配方|查询配方)", text)
    )


def _is_formula_selection(text: str) -> bool:
    return "配方" in text and _contains_any(text, FORMULA_SELECT_WORDS)


def _is_bottle_query(text: str) -> bool:
    """
    判断是否为瓶子查询意图。
    必须同时满足：
    1. 包含瓶子相关名词
    2. 包含明确的查询动作词
    3. 不包含任务动作词（称、分装、混合等）
    """
    has_bottle_noun = re.search(r"(试剂瓶|空瓶|瓶子|瓶列表|瓶管理)", text)
    has_query_verb = re.search(r"(查询|查一下|查查|查看|看看|看下|帮我查|列出|显示|有哪些|有几个|列表|管理)", text)
    has_task_verb = re.search(r"(称|称量|称取|称重|分装|分料|分成|混合|配制|放到|放入|倒入|加入)", text)

    return bool(has_bottle_noun and has_query_verb and not has_task_verb)


def _needs_catalog_candidate(active_draft: TaskDraftRecord) -> bool:
    return any(
        field in active_draft.pending_confirmation_fields
        for field in ("catalog_candidate", "chemical_id")
    )


def _is_catalog_selection(text: str) -> bool:
    return bool(
        re.search(r"(选择|选|用|确认|第\s*[一二三四五六七八九十\d]+|CHEM_[A-Za-z0-9_]+)", text, re.I)
    )


def _extract_drug_keyword(text: str) -> str:
    """从库存查询文本中剥离查询功能词，提取可能的药品名。"""
    t = _QUERY_PREFIX_RE.sub("", text.strip())
    t = _QUERY_SUFFIX_RE.sub("", t)
    return t.strip() or text.strip()


def _looks_like_task_seed(text: str) -> bool:
    return bool(re.search(r"(我要|帮我|来点|一点|乙醇|氯化钠|葡萄糖|毫克|克|mg|g)", text, re.I))


def _detect_signals(text: str) -> list[str]:
    """检测文本中的意图信号"""
    signals = []

    # 任务动作信号
    if _contains_any(text, WEIGHING_WORDS):
        signals.append("weighing_action")
    if _contains_any(text, DISPENSING_WORDS):
        signals.append("dispensing_action")
    if _contains_any(text, MIXING_WORDS):
        signals.append("mixing_action")

    # 查询动作信号
    if re.search(r"(查询|查一下|查查|查看|看看|看下|列出|显示|有哪些|有几个)", text):
        signals.append("query_verb")

    # 确认/取消信号
    if _contains_any(text, CONFIRM_WORDS):
        signals.append("confirm_word")
    if _contains_any(text, CANCEL_WORDS):
        signals.append("cancel_word")

    # 参数信号
    if re.search(r"\d+\s*(mg|g|kg|毫克|克|千克)", text, re.I):
        signals.append("mass")
    if re.search(r"(氯化钠|乙醇|葡萄糖|碳酸氢钠|氯化钾)", text):
        signals.append("chemical")
    if re.search(r"(空瓶|试剂瓶|瓶子|工位|容器)\d*", text):
        signals.append("vessel_text")
    if re.search(r"\d+\s*(管|瓶|份|个)", text):
        signals.append("portion_count")

    # 对象名词信号
    if re.search(r"(试剂瓶|空瓶|瓶子|瓶列表|瓶管理)", text):
        signals.append("bottle_word_present")
    if re.search(r"(配方|配方列表)", text):
        signals.append("formula_word")

    return signals


def _detect_conflicts(text: str, signals: list[str]) -> list[str]:
    """检测意图冲突"""
    conflicts = []

    # 多个任务动作冲突
    task_actions = [s for s in signals if s.endswith("_action")]
    if len(task_actions) > 1:
        conflicts.append("multiple_task_actions")

    # 任务动作 + 查询动词冲突
    if any(s.endswith("_action") for s in signals) and "query_verb" in signals:
        conflicts.append("task_vs_query")

    # 瓶子词 + 任务动作（不是真冲突，任务优先）
    if "bottle_word_present" in signals and any(s.endswith("_action") for s in signals):
        conflicts.append("bottle_word_with_task")

    return conflicts


def _calculate_confidence(
    route: Route,
    task_type: TaskType | None,
    signals: list[str],
    conflicts: list[str],
    active_draft: TaskDraftRecord | None,
) -> float:
    """计算路由置信度 (0.0 - 1.0)"""
    base_confidence = 0.5

    # 强规则：明确动作 + 参数
    if route == "start_task":
        if task_type == TaskType.WEIGHING:
            if "weighing_action" in signals:
                base_confidence = 0.85
                if "mass" in signals:
                    base_confidence += 0.05
                if "chemical" in signals:
                    base_confidence += 0.05
                if "vessel_text" in signals:
                    base_confidence += 0.03
        elif task_type == TaskType.DISPENSING:
            if "dispensing_action" in signals:
                base_confidence = 0.85
                if "portion_count" in signals:
                    base_confidence += 0.05
                if "vessel_text" in signals:
                    base_confidence += 0.03

    # 查询类：需要明确查询动词
    elif route in ("query_bottles", "query_inventory", "query_formula"):
        if "query_verb" in signals:
            base_confidence = 0.80
        else:
            base_confidence = 0.50  # 只有对象名词，没有查询动词

    # 确认/取消：依赖 active_draft
    elif route in ("confirm_task", "confirm_fields", "cancel_task"):
        if active_draft:
            base_confidence = 0.90
        else:
            base_confidence = 0.30

    # update_task：active_draft 存在时高置信
    elif route == "update_task":
        if active_draft:
            base_confidence = 0.85
        else:
            base_confidence = 0.20

    # clarify：低置信
    elif route == "clarify":
        base_confidence = 0.40

    # 冲突降低置信度
    if "multiple_task_actions" in conflicts:
        base_confidence -= 0.15
    if "task_vs_query" in conflicts:
        base_confidence -= 0.10

    # 任务动作优先于瓶子词，不降置信
    if "bottle_word_with_task" in conflicts:
        pass  # 不降置信，这是预期的优先级

    return max(0.0, min(1.0, base_confidence))
