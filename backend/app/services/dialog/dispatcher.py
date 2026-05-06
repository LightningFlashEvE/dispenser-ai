"""IntentDispatcher —— 统一 Orchestrator，把 WebSocket 层的业务逻辑收敛。

设计目标（v2）：
- channels.py 只做消息路由 + 状态推送，所有业务逻辑走 dispatcher
- 一轮用户输入只做一次"主理解"，不再前台+后台各跑一套
- 明确的 OutputType 决定本轮输出方向，替代隐式的关键词分支
- 状态驱动确认逻辑：session.state == "awaiting_confirmation" 时，
  由 LLM interpret_confirmation() 而非关键词判断用户意图

两阶段对话（保留 AGENTS.md 的安全约束）：
  1. dialog 阶段：LLM 流式输出自然语言回复（channels._stream_dialog_with_tts）
  2. resolve_intent 阶段：LLM 解析意图（串行，隐藏在 TTS 播放延迟之后）
     → 若完整 → 生成 pending_intent（session 进入 awaiting_confirmation）
     → 若 query/紧急 → 立即执行
     → 若不完整 → 无 pending，继续对话

Orchestrator 输出类型（OutputType）：
  reply               — 普通自然语言回复（无意图）
  question            — AI 要求用户补充信息
  action_proposal     — 推送 pending_intent，等待确认
  confirmation_required — 重新确认（pending 修改后）
  execute_now         — 直接执行（query/紧急类）
  reject              — 拒绝执行（校验失败/设备不就绪）
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.task import Task
from app.services.ai.llm import DialogResult, IntentResult, LLMService
from app.services.dialog.intent import INTENT_TYPES_NO_SLOTS, validate_intent
from app.services.dialog.rules import build_command
from app.services.dialog.session import PendingIntent, Session
from app.services.dialog.state_machine import StateMachine
from app.services.device.control_client import ControlClient
from app.services.inventory.drug_lookup import drug_to_dict, find_best_drug

logger = logging.getLogger(__name__)


OutputType = Literal[
    "reply",
    "question",
    "action_proposal",
    "confirmation_required",
    "execute_now",
    "reject",
]

DispatchState = Literal[
    "IDLE", "LISTENING", "PROCESSING", "ASKING", "EXECUTING", "FEEDBACK", "ERROR"
]


# ─── DispatchResult ───────────────────────────────────────────────

@dataclass
class DispatchResult:
    """一次 dispatch 的完整反馈。channels.py 依据此输出 WS 消息。"""

    speak_text: str | None = None
    dialog_text: str | None = None
    state: DispatchState = "IDLE"
    output_type: OutputType = "reply"
    error_code: str | None = None
    error_message: str | None = None
    pending_payload: dict | Literal["clear"] | None = None
    slot_filling: dict | None = None
    command_id: str | None = None
    debug: dict[str, Any] = field(default_factory=dict)
    pending_only: bool = False


# query/紧急类意图，LLM 识别到即立即执行（不走 pending 确认）
AUTO_EXECUTE_INTENTS: set[str] = {
    "query_stock",
    "query_formula",
    "device_status",
    "emergency_stop",
    "cancel",
    "formula",
}


# ─── IntentDispatcher ────────────────────────────────────────────

class IntentDispatcher:
    """将文本输入（来自 ASR 或直接输入）转换为 DispatchResult。"""

    def __init__(
        self,
        llm: LLMService,
        state_machine: StateMachine,
        control_client: ControlClient,
    ) -> None:
        self._llm = llm
        self._sm = state_machine
        self._control = control_client

    @property
    def llm(self) -> LLMService:
        """暴露给 channels._stream_dialog_with_tts 使用。"""
        return self._llm

    # ─── 普通对话入口（非流式，供回退或确认路径使用） ─────────────

    async def handle_user_input(self, session: Session, user_text: str) -> DispatchResult:
        """非流式对话路径（回退 / 确认路径调用）。"""
        text = user_text.strip()
        if not text:
            return DispatchResult(
                error_code="EMPTY_INPUT",
                error_message="输入文本为空",
                state="ERROR",
            )

        if session.is_over_limit(settings.dialog_max_rounds):
            session.reset()
            return DispatchResult(
                speak_text="对话轮数过多，已重置，请重新描述您的操作",
                state="IDLE",
                pending_payload="clear",
            )

        session.add_user_dialog(text)

        import time as _t
        _t0 = _t.time()

        dialog_result = await self._llm.process_dialog(
            user_text=text,
            dialog_history=session.dialog_history[:-1],
        )
        logger.info(
            "[handle_user_input] dialog done elapsed=%.1fs error=%s",
            _t.time() - _t0, dialog_result.error,
        )
        if dialog_result.error:
            return DispatchResult(
                error_code="LLM_ERROR",
                error_message=dialog_result.error,
                state="ERROR",
            )

        reply = dialog_result.text or "我正在思考..."
        session.add_assistant_dialog(reply)

        return DispatchResult(
            dialog_text=reply,
            speak_text=reply,
            state="ASKING",
            output_type="reply",
        )

    # ─── 串行 Intent 解析（P4：Orchestrator 统一入口） ───────────

    async def try_auto_resolve(
        self, session: Session, user_text: str
    ) -> DispatchResult | None:
        """轻量异步 intent 解析——供 channels.py 在流式对话结束后调用。

        只执行自动执行类意图（query_stock/formula/device_status 等），
        不返回 pending 类型的 DispatchResult。
        """
        import time as _t
        _t0 = _t.time()

        try:
            intent_result = await self._llm.process_intent(user_text=user_text)
        except Exception as e:
            logger.warning("[try_auto_resolve] process_intent exception: %s", e)
            return None

        logger.info(
            "[try_auto_resolve] done elapsed=%.1fs error=%s intent_type=%s",
            _t.time() - _t0,
            intent_result.error,
            (intent_result.raw_json or {}).get("intent_type"),
        )

        auto_exec = await self._try_auto_execute(session, intent_result)
        if auto_exec is not None:
            return auto_exec
        return None

    async def resolve_intent(
        self, session: Session, user_text: str
    ) -> DispatchResult | None:
        """串行 intent 解析 —— 由 channels 在 TTS 播放后调用，不再后台并发。"""
        import time as _t
        _t0 = _t.time()

        try:
            intent_result = await self._llm.process_intent(user_text=user_text)
        except Exception as e:
            logger.warning("[resolve_intent] process_intent exception: %s", e)
            return None

        logger.info(
            "[resolve_intent] done elapsed=%.1fs error=%s intent_type=%s",
            _t.time() - _t0,
            intent_result.error,
            (intent_result.raw_json or {}).get("intent_type"),
        )

        try:
            auto_exec = await self._try_auto_execute(session, intent_result)
        except Exception as e:
            logger.warning("[resolve_intent] auto_execute exception: %s", e)
            auto_exec = None
        if auto_exec is not None:
            return auto_exec

        try:
            pending = await self._pending_from_intent(session, intent_result)
        except Exception as e:
            logger.warning("[resolve_intent] pending_from_intent exception: %s", e)
            return None
        if pending is None:
            return None

        return DispatchResult(
            pending_payload=pending.to_wire(),
            state="ASKING",
            output_type="action_proposal",
            pending_only=True,
        )

    async def resolve_intent_from_dialog(
        self, session: Session
    ) -> DispatchResult:
        """从对话历史解析意图 —— 用户点击"确认执行"后调用。

        流程：
        1. 把 session.dialog_history 传给 LLM 解析意图
        2. 校验 intent → 生成 pending → 直接执行
        3. 如果信息不足，返回反问
        """
        import time as _t
        _t0 = _t.time()

        try:
            intent_result = await self._llm.process_intent_from_dialog(
                dialog_history=session.dialog_history
            )
        except Exception as e:
            logger.warning("[resolve_intent_from_dialog] exception: %s", e)
            return DispatchResult(
                error_code="INTENT_PARSE_ERROR",
                error_message="意图解析失败，请重试",
                state="ERROR",
            )

        logger.info(
            "[resolve_intent_from_dialog] done elapsed=%.1fs error=%s intent_type=%s",
            _t.time() - _t0,
            intent_result.error,
            (intent_result.raw_json or {}).get("intent_type"),
        )

        if intent_result.error:
            return DispatchResult(
                error_code="INTENT_PARSE_ERROR",
                error_message=intent_result.error,
                state="ERROR",
            )

        # 信息不完整，需要补槽
        if not intent_result.is_complete:
            question = intent_result.clarification_question or "请补充更多信息"
            return DispatchResult(
                speak_text=question,
                dialog_text=question,
                state="ASKING",
                output_type="question",
            )

        # 尝试自动执行（query/紧急类）
        try:
            auto_exec = await self._try_auto_execute(session, intent_result)
        except Exception as e:
            logger.warning("[resolve_intent_from_dialog] auto_execute exception: %s", e)
            auto_exec = None
        if auto_exec is not None:
            return auto_exec

        # 生成 pending 并立即执行
        try:
            pending = await self._pending_from_intent(session, intent_result)
        except Exception as e:
            logger.warning("[resolve_intent_from_dialog] pending_from_intent exception: %s", e)
            return DispatchResult(
                error_code="INTENT_BUILD_ERROR",
                error_message="无法构建执行指令",
                state="ERROR",
            )

        if pending is None:
            return DispatchResult(
                error_code="INTENT_BUILD_ERROR",
                error_message="无法识别有效操作",
                state="ERROR",
            )

        # 直接执行，不再等待二次确认
        return await self._execute_pending(session, pending)

    async def create_pending_from_intent(
        self,
        session: Session,
        intent_data: dict[str, Any],
    ) -> DispatchResult:
        """Create a backend-owned pending proposal from a validated draft intent.

        The draft layer owns field completeness. This method only converts the
        formal backend intent into the existing pending approval object.
        """
        pending = await self._pending_from_intent(
            session,
            IntentResult(raw_json=intent_data, is_complete=True),
        )
        if pending is None:
            return DispatchResult(
                error_code="INTENT_BUILD_ERROR",
                error_message="无法根据任务草稿生成正式 proposal",
                state="ERROR",
            )
        return DispatchResult(
            pending_payload=pending.to_wire(),
            state="ASKING",
            output_type="action_proposal",
            pending_only=True,
        )

    # ─── 确认态输入解析（P3：状态驱动） ─────────────────────────

    async def handle_confirmation_input(
        self, session: Session, user_text: str
    ) -> DispatchResult:
        """当 session.state == awaiting_confirmation 时处理用户输入。"""
        if not session.has_active_pending():
            session.transition_to("idle")
            return await self.handle_user_input(session, user_text)

        pending_summary = session.pending.summary() if session.pending else ""
        intent_label = await self._llm.interpret_confirmation(
            user_text=user_text,
            pending_summary=pending_summary,
        )
        logger.info(
            "[confirmation_input] interpret=%s text=%r", intent_label, user_text[:50]
        )

        if intent_label == "confirm":
            return await self.handle_confirm(session)
        if intent_label == "cancel":
            return await self.handle_cancel_pending(session)
        if intent_label == "modify":
            session.clear_pending()
            return await self.handle_user_input(session, user_text)
        return await self.handle_user_input(session, user_text)

    # ─── 确认/取消执行 ───────────────────────────────────────────

    async def handle_confirm(self, session: Session) -> DispatchResult:
        pending = session.consume_pending()
        if pending is None:
            return DispatchResult(
                speak_text="没有待确认的任务，请先描述您要执行的操作",
                state="IDLE",
                pending_payload="clear",
                output_type="reject",
            )
        return await self._execute_pending(session, pending)

    async def handle_cancel_pending(self, session: Session) -> DispatchResult:
        had = session.has_active_pending()
        session.clear_pending()
        cancel_text = "已取消待执行的任务" if had else None
        return DispatchResult(
            dialog_text=cancel_text,
            speak_text=cancel_text,
            state="IDLE",
            pending_payload="clear",
            output_type="reject",
        )

    async def handle_cancel_current_task(self, session: Session) -> DispatchResult:
        current_task = await _load_current_task(self._sm)
        if current_task is None or not current_task.command_id:
            return DispatchResult(
                dialog_text="当前没有可取消的任务",
                speak_text="当前没有可取消的任务",
                state="IDLE",
                output_type="reject",
            )

        cancel_command = {
            "schema_version": "2.1",
            "command_id": str(uuid.uuid4()),
            "timestamp": _now_iso(),
            "operator_id": "admin",
            "command_type": "cancel",
            "payload": {"target_command_id": current_task.command_id},
        }
        ok, reason = await self._control.send_command(cancel_command)
        if not ok:
            return DispatchResult(
                error_code="CANCEL_FAILED",
                error_message=reason or "取消指令下发失败",
                state="ERROR",
                output_type="reject",
            )
        self._sm.cancel_task(current_task.task_id)
        session.reset()
        return DispatchResult(
            dialog_text="任务已取消",
            speak_text="任务已取消",
            command_id=current_task.command_id,
            state="IDLE",
            pending_payload="clear",
            output_type="execute_now",
        )

    # ─── 内部：意图 → pending / 自动执行 ─────────────────────────

    async def _try_auto_execute(
        self, session: Session, intent_result: IntentResult
    ) -> DispatchResult | None:
        if intent_result.error or intent_result.raw_json is None:
            return None
        intent_data = intent_result.raw_json
        intent_type = intent_data.get("intent_type")
        if intent_type not in AUTO_EXECUTE_INTENTS:
            return None

        is_valid, _errors, _clar = validate_intent(intent_data, strict_schema=False)
        if not is_valid:
            return None

        if intent_type == "device_status":
            return await self.handle_query_device_status(session)
        if intent_type in ("query_stock", "query_formula"):
            keyword = (
                (intent_data.get("params") or {}).get("raw_text")
                or (intent_data.get("reagent_hint") or {}).get("raw_text")
            )
            if intent_type == "query_stock":
                return await self.handle_query_stock(session, keyword)
            return await self.handle_query_formula(session, keyword)
        if intent_type == "formula":
            keyword = (
                (intent_data.get("params") or {}).get("raw_text")
                or (intent_data.get("reagent_hint") or {}).get("raw_text")
            )
            return await self.handle_query_formula(session, keyword)
        if intent_type == "emergency_stop":
            return await self.handle_emergency_stop(session)
        if intent_type == "cancel":
            return await self.handle_cancel_current_task(session)
        return None

    async def _pending_from_intent(
        self, session: Session, intent_result: IntentResult
    ) -> PendingIntent | None:
        if intent_result.error or intent_result.raw_json is None:
            logger.debug("intent 阶段未返回可用 JSON: %s", intent_result.error)
            return None

        intent_data = intent_result.raw_json
        is_valid, errors, clarification = validate_intent(intent_data, strict_schema=False)
        if clarification:
            logger.debug("LLM 要求补槽: %s", clarification)
            return None
        if not is_valid:
            logger.info("intent 业务校验失败: %s", errors)
            return None

        intent_type = intent_data.get("intent_type")
        if intent_type == "unknown" or intent_type in AUTO_EXECUTE_INTENTS:
            return None

        drug_info: dict | None = None
        if intent_type in {"dispense", "aliquot", "restock"}:
            reagent_hint = intent_data.get("reagent_hint") or {}
            drug, score = await find_best_drug(reagent_hint.get("raw_text"))
            if drug is None or score < 0.5:
                logger.info(
                    "未找到药品：%s (score=%.2f)", reagent_hint.get("raw_text"), score
                )
                return None
            drug_info = drug_to_dict(drug)

        if intent_type == "mix":
            ok, err_msg = await self._resolve_mix_components(intent_data)
            if not ok:
                logger.info("mix 组分解析失败: %s", err_msg)
                return None

        return session.set_pending(
            intent_data=intent_data,
            drug_info=drug_info,
            ttl_seconds=settings.pending_intent_ttl_sec,
        )

    async def _execute_pending(
        self, session: Session, pending: PendingIntent
    ) -> DispatchResult:
        intent_data = pending.intent_data
        drug_info = pending.drug_info

        can_start, reason = self._sm.can_start_task()
        if not can_start:
            return DispatchResult(
                error_code="DEVICE_BUSY",
                error_message=reason,
                state="ERROR",
                output_type="reject",
            )

        try:
            command = await build_command(intent_data, drug_info)
        except ValueError as e:
            logger.exception("build_command 失败")
            return DispatchResult(
                error_code="COMMAND_BUILD_FAILED",
                error_message=str(e),
                state="ERROR",
                output_type="reject",
            )

        task_id = await _create_task_record(intent_data, command)
        if not self._sm.start_task(task_id):
            await _update_task_failure(task_id, "状态机拒绝启动任务")
            return DispatchResult(
                error_code="STATE_MACHINE_REJECTED",
                error_message="状态机拒绝启动任务",
                state="ERROR",
                output_type="reject",
            )

        ok, reason = await self._control.send_command(command)
        if not ok:
            self._sm.fail_task(task_id, reason or "命令下发失败")
            await _update_task_failure(task_id, reason or "命令下发失败")
            return DispatchResult(
                error_code="COMMAND_SEND_FAILED",
                error_message=reason or "命令下发失败",
                state="ERROR",
                output_type="reject",
            )

        session.reset()
        return DispatchResult(
            command_id=command["command_id"],
            state="EXECUTING",
            pending_payload="clear",
            speak_text="已下发指令，正在执行",
            output_type="execute_now",
        )

    # ─── 查询类直接执行 ──────────────────────────────────────────

    async def handle_query_device_status(self, session: Session) -> DispatchResult:
        status = await self._control.get_status()
        text = (
            f"设备状态：{status.get('device_status', 'unknown')}，"
            f"天平就绪：{status.get('balance_ready', False)}"
        )
        session.reset()
        return DispatchResult(
            dialog_text=text, speak_text=text,
            state="FEEDBACK", pending_payload="clear", output_type="execute_now",
        )

    async def handle_query_stock(
        self, session: Session, keyword: str | None
    ) -> DispatchResult:
        query = _normalize_stock_keyword(keyword)

        # 通用库存查询：查所有活跃药品
        if query is None:
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select
                from app.models.drug import Drug

                result = await db.execute(
                    select(Drug)
                    .where(Drug.is_active == True)  # noqa: E712
                    .order_by(Drug.stock_mg.asc())
                )
                drugs = list(result.scalars().all())

            session.reset()

            if not drugs:
                text = "当前没有可用药品库存记录"
                return DispatchResult(
                    dialog_text=text,
                    speak_text=text,
                    state="FEEDBACK",
                    pending_payload="clear",
                    output_type="reply",
                )

            low_drugs = [d for d in drugs if d.stock_mg < 1000]
            preview = drugs[:8]

            items = "；".join(
                f"{d.reagent_name_cn} {d.stock_mg} mg，工位 {d.station_id or '未知'}"
                for d in preview
            )

            text = (
                f"当前共有 {len(drugs)} 种活跃药品，"
                f"其中低库存药品 {len(low_drugs)} 种。"
                f"库存较低的药品有：{items}。"
            )

            if len(drugs) > len(preview):
                text += "更多库存请在药品库存页面查看。"

            return DispatchResult(
                dialog_text=text,
                speak_text=text,
                state="FEEDBACK",
                pending_payload="clear",
                output_type="execute_now",
            )

        # 具体药品库存查询
        drug, score = await find_best_drug(query)
        session.reset()

        if drug is None or score < 0.5:
            return DispatchResult(
                dialog_text=f"没有找到药品：{query}",
                speak_text=f"没有找到药品：{query}",
                state="FEEDBACK", pending_payload="clear", output_type="reply",
            )

        text = (
            f"{drug.reagent_name_cn} 当前库存 {drug.stock_mg} mg，"
            f"工位 {drug.station_id or '未知'}"
        )

        return DispatchResult(
            dialog_text=text,
            speak_text=text,
            state="FEEDBACK", pending_payload="clear", output_type="execute_now",
        )

    async def handle_query_formula(
        self, session: Session, keyword: str | None
    ) -> DispatchResult:
        if not keyword:
            return DispatchResult(
                dialog_text="请提供要查询的配方名称",
                speak_text="请提供要查询的配方名称",
                state="ASKING", output_type="question",
            )
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.models.formula import Formula, FormulaStep
            stmt = (
                select(Formula)
                .options(selectinload(Formula.steps))
                .order_by(Formula.formula_name)
            )
            result = await db.execute(stmt)
            all_formulas: list[Formula] = list(result.scalars().all())

        if not all_formulas:
            session.reset()
            return DispatchResult(
                dialog_text="当前没有可用配方",
                speak_text="当前没有可用配方",
                state="FEEDBACK", pending_payload="clear", output_type="reply",
            )

        kw = keyword.lower().strip()
        scored: list[tuple[Formula, float]] = []
        for f in all_formulas:
            if f.formula_id.lower() == kw or f.formula_name.lower() == kw:
                score = 1.0
            elif f.formula_id.lower().startswith(kw) or f.formula_name.lower().startswith(kw):
                score = 0.9
            elif kw in [alias.lower() for alias in f.aliases_list]:
                score = 0.95
            elif any(kw in alias.lower() for alias in f.aliases_list):
                score = 0.7
            elif kw in f.formula_name.lower():
                score = 0.5
            else:
                score = 0.0
            if score > 0:
                scored.append((f, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        if not scored:
            session.reset()
            return DispatchResult(
                dialog_text=f"没有找到配方：{keyword}",
                speak_text=f"没有找到配方：{keyword}",
                state="FEEDBACK", pending_payload="clear", output_type="reply",
            )

        best_formula, best_score = scored[0]

        if best_score < 0.5 and len(scored) > 1:
            best_formula, best_score = scored[0]

        step_count = len(best_formula.steps)
        formula_info = {
            "formula_id": best_formula.formula_id,
            "formula_name": best_formula.formula_name,
            "aliases_list": best_formula.aliases_list,
            "step_count": step_count,
            "steps": [
                {
                    "step_index": s.step_index,
                    "step_name": s.step_name,
                    "command_type": s.command_type,
                    "reagent_code": s.reagent_code,
                    "target_mass_mg": s.target_mass_mg,
                    "tolerance_mg": s.tolerance_mg,
                    "target_vessel": s.target_vessel,
                }
                for s in sorted(best_formula.steps, key=lambda x: x.step_index)
            ],
        }

        if keyword:
            speak_text = (
                f"找到配方：{best_formula.formula_name}，"
                f"共 {step_count} 步"
            )
        else:
            speak_text = (
                f"配方：{best_formula.formula_name}，"
                f"共 {step_count} 步"
            )

        session.reset()
        return DispatchResult(
            dialog_text=speak_text,
            speak_text=speak_text,
            state="FEEDBACK",
            pending_payload="clear",
            output_type="execute_now",
            debug={"formula_info": formula_info},
        )

    async def handle_emergency_stop(self, session: Session) -> DispatchResult:
        self._sm.trigger_emergency_stop()
        ok, reason = await self._control.send_emergency_stop()
        if not ok:
            return DispatchResult(
                error_code="EMERGENCY_STOP_FAILED",
                error_message=reason or "急停指令下发失败",
                state="ERROR", output_type="reject",
            )
        session.reset()
        return DispatchResult(
            dialog_text="急停已触发", speak_text="急停已触发",
            command_id="emergency_stop",
            state="FEEDBACK", pending_payload="clear", output_type="execute_now",
        )

    # ─── 工具函数 ────────────────────────────────────────────────

    async def _resolve_mix_components(self, intent_data: dict) -> tuple[bool, str | None]:
        params = intent_data.get("params", {}) or {}
        components = params.get("components") or []
        total_mass_mg = params.get("total_mass_mg")
        ratio_type = params.get("ratio_type") or "mass_fraction"
        if not isinstance(components, list) or not isinstance(total_mass_mg, int) or total_mass_mg <= 0:
            return False, "混合参数不完整"
        if len(components) < 2:
            return False, "混合至少需要 2 个组分"

        resolved: list[dict] = []

        if ratio_type == "molar_fraction":
            weights: list[float] = []
            matched: list[Any] = []
            weighted_sum = 0.0
            for comp in components:
                drug, score = await find_best_drug(comp.get("raw_text"))
                if drug is None or score < 0.5:
                    return False, f"未找到组分药品：{comp.get('raw_text')}"
                if not drug.molar_weight_g_mol or drug.molar_weight_g_mol <= 0:
                    return False, f"组分缺少摩尔质量：{drug.reagent_name_cn}"
                fraction = comp.get("fraction")
                if not isinstance(fraction, (int, float)):
                    return False, f"组分占比无效：{comp.get('raw_text')}"
                weight = float(fraction) * float(drug.molar_weight_g_mol)
                weights.append(weight)
                weighted_sum += weight
                matched.append(drug)
            if weighted_sum <= 0:
                return False, "摩尔分数无法换算质量"
            for comp, drug, weight in zip(components, matched, weights):
                calc_mass = max(1, round(total_mass_mg * weight / weighted_sum))
                resolved.append(
                    {
                        **drug_to_dict(drug),
                        "fraction": comp.get("fraction"),
                        "calculated_mass_mg": calc_mass,
                        "tolerance_mg": _default_tolerance(calc_mass),
                    }
                )
        else:
            for comp in components:
                drug, score = await find_best_drug(comp.get("raw_text"))
                if drug is None or score < 0.5:
                    return False, f"未找到组分药品：{comp.get('raw_text')}"
                fraction = comp.get("fraction")
                if not isinstance(fraction, (int, float)):
                    return False, f"组分占比无效：{comp.get('raw_text')}"
                calc_mass = max(1, round(total_mass_mg * float(fraction)))
                resolved.append(
                    {
                        **drug_to_dict(drug),
                        "fraction": fraction,
                        "calculated_mass_mg": calc_mass,
                        "tolerance_mg": _default_tolerance(calc_mass),
                    }
                )

        intent_data.setdefault("params", {})["components"] = resolved
        return True, None


# ─── DB 工具 ─────────────────────────────────────────────────────

async def _create_task_record(intent_data: dict, command: dict) -> str:
    task_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        task = Task(
            task_id=task_id,
            command_id=command["command_id"],
            command_type=command["command_type"],
            operator_id=command.get("operator_id", "admin"),
            status="EXECUTING",
            intent_json=json.dumps(intent_data, ensure_ascii=False),
            command_json=json.dumps(command, ensure_ascii=False),
            started_at=datetime.now(timezone.utc),
        )
        db.add(task)
        await db.commit()
    return task_id


async def _update_task_failure(task_id: str, message: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return
        task.status = "FAILED"
        task.error_message = message
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _load_current_task(sm: StateMachine) -> Task | None:
    task_id = sm.current_task_id
    if not task_id:
        return None
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.task_id == task_id))
        return result.scalar_one_or_none()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_stock_keyword(text: str | None) -> str | None:
    """把库存查询语句归一化成药品关键词；返回 None 表示查全部库存。"""
    if not text:
        return None

    import re

    raw = text.strip()
    if not raw:
        return None

    # 明确表示"全部库存"的说法
    generic_patterns = (
        r"^(查看|查询|看一下|帮我看一下|帮我查一下)?(当前|全部|所有|整体)?药品库存(情况|列表)?$",
        r"^(查看|查询|看一下|帮我看一下|帮我查一下)?(当前|全部|所有|整体)?库存(情况|列表)?$",
        r"^药品库存$",
        r"^库存$",
        r"^所有药品$",
        r"^全部药品$",
    )
    if any(re.search(p, raw) for p in generic_patterns):
        return None

    # 去掉库存查询里的功能词，剩下的当药品名/编号/别名
    cleaned = re.sub(
        r"(查看|查询|看一下|帮我看一下|帮我查一下|当前|药品|库存|还有多少|剩多少|还剩多少|的|一下|请|帮我)",
        "",
        raw,
    )
    cleaned = cleaned.strip(" ，。！？?")

    # 剩下还是通用词，也查全部
    if cleaned in {"", "所有", "全部", "当前", "全部药品", "所有药品"}:
        return None

    return cleaned


def _default_tolerance(mass_mg: int) -> int:
    if mass_mg <= 100:
        return max(1, round(mass_mg * 0.05))
    if mass_mg <= 1000:
        return max(5, round(mass_mg * 0.03))
    return max(20, round(mass_mg * 0.02))


__all__ = [
    "IntentDispatcher",
    "DispatchResult",
    "OutputType",
    "AUTO_EXECUTE_INTENTS",
]
