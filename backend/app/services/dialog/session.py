"""对话会话 —— 内存态 Session 管理。

设计要点：
- 一个 WebSocket 连接对应一个 Session 实例（进程生命周期内存活）。
- dialog_history 与 intent_history 分离：
    * dialog_history: 自然语言闲聊 / 反问补槽，注入给 process_dialog()
    * intent_history: 备用（当前 intent 阶段为单轮调用，不依赖历史）
- pending_intent 机制取代关键词匹配：
    1. LLM 解析出 is_complete=true 且校验通过 → 生成 pending snapshot
    2. WebSocket 推 pending_intent 给前端
    3. 用户点击确认或说确认语句 → 后端从 session 取，不再调 LLM
    4. 60s 未确认自动过期，释放
- SessionState 状态机：
    驱动"确认态解析"逻辑，替代关键词硬判断。
    state == "awaiting_confirmation" + has_active_pending()
    → 用户输入先走 interpret_confirmation()，不再做关键词匹配。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal


# ─── SessionState ────────────────────────────────────────────────

SessionState = Literal[
    "idle",
    "listening",
    "recognizing",
    "thinking",
    "speaking",
    "awaiting_confirmation",
    "interrupted",
]

_VALID_TRANSITIONS: dict[SessionState, set[SessionState] | None] = {
    "idle":                  None,
    "listening":             {"idle", "interrupted", "speaking", "awaiting_confirmation"},
    "recognizing":           {"listening"},
    "thinking":              {"recognizing", "idle"},
    "speaking":              {"thinking"},
    "awaiting_confirmation": {"thinking", "speaking"},
    "interrupted":           None,
}


DEFAULT_PENDING_TTL_SECONDS = 60
DEFAULT_DIALOG_HISTORY_MAX_MESSAGES = 16


# ─── PendingIntent ────────────────────────────────────────────────

@dataclass
class PendingIntent:
    """一次等待用户确认的意图快照。"""

    intent_data: dict[str, Any]
    drug_info: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
        + timedelta(seconds=DEFAULT_PENDING_TTL_SECONDS)
    )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def to_wire(self) -> dict[str, Any]:
        intent = self.intent_data
        return {
            "intent_id": intent.get("intent_id"),
            "intent_type": intent.get("intent_type"),
            "params": intent.get("params", {}),
            "reagent_hint": intent.get("reagent_hint"),
            "drug": {
                "reagent_code": (self.drug_info or {}).get("reagent_code"),
                "reagent_name_cn": (self.drug_info or {}).get("reagent_name_cn"),
                "station_id": (self.drug_info or {}).get("station_id"),
            } if self.drug_info else None,
            "expires_at": self.expires_at.isoformat(),
        }

    def summary(self) -> str:
        """给 interpret_confirmation() 使用的简短描述。"""
        intent = self.intent_data
        intent_type = intent.get("intent_type", "未知操作")
        params = intent.get("params") or {}
        drug = self.drug_info or {}
        parts = [f"操作类型：{intent_type}"]
        if drug.get("reagent_name_cn"):
            parts.append(f"药品：{drug['reagent_name_cn']}")
        if params.get("target_mass_mg"):
            parts.append(f"目标质量：{params['target_mass_mg']} mg")
        if drug.get("station_id"):
            parts.append(f"工位：{drug['station_id']}")
        return "，".join(parts)


# ─── Session ──────────────────────────────────────────────────────

class Session:
    """单个 WebSocket 连接的对话状态。"""

    def __init__(
        self,
        session_id: str,
        history_max_messages: int = DEFAULT_DIALOG_HISTORY_MAX_MESSAGES,
    ):
        self.session_id = session_id
        self.dialog_history: list[dict[str, str]] = []
        self.intent_history: list[dict[str, str]] = []
        self.round_count: int = 0
        self.pending: PendingIntent | None = None
        self._history_max_messages = max(2, history_max_messages)
        self.state: SessionState = "idle"

    # ─── 状态机 ───────────────────────────────────────────────────

    def transition_to(self, new_state: SessionState) -> bool:
        allowed = _VALID_TRANSITIONS.get(new_state)
        if allowed is None or self.state in allowed:
            self.state = new_state
            return True
        if new_state in ("idle", "interrupted"):
            self.state = new_state
            return True
        import logging
        logging.getLogger(__name__).debug(
            "Session %s: 忽略非法状态转移 %s → %s",
            self.session_id, self.state, new_state,
        )
        self.state = new_state
        return False

    # ─── 对话历史 ─────────────────────────────────────────────────

    def add_user_dialog(self, text: str) -> None:
        self.dialog_history.append({"role": "user", "content": text})
        self.round_count += 1
        self._trim_dialog_history()

    def add_assistant_dialog(self, text: str) -> None:
        self.dialog_history.append({"role": "assistant", "content": text})
        self._trim_dialog_history()

    def _trim_dialog_history(self) -> None:
        overflow = len(self.dialog_history) - self._history_max_messages
        if overflow > 0:
            if overflow % 2 == 1:
                overflow += 1
            self.dialog_history = self.dialog_history[overflow:]

    def add_user_intent(self, text: str) -> None:
        self.intent_history.append({"role": "user", "content": text})

    def add_assistant_intent(self, json_str: str) -> None:
        self.intent_history.append({"role": "assistant", "content": json_str})

    # ─── Pending intent ──────────────────────────────────────────

    def set_pending(
        self,
        intent_data: dict[str, Any],
        drug_info: dict[str, Any] | None = None,
        ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
    ) -> PendingIntent:
        now = datetime.now(timezone.utc)
        self.pending = PendingIntent(
            intent_data=intent_data,
            drug_info=drug_info,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.transition_to("awaiting_confirmation")
        return self.pending

    def consume_pending(self) -> PendingIntent | None:
        p = self.pending
        self.pending = None
        if p is None or p.is_expired():
            return None
        return p

    def clear_pending(self) -> None:
        self.pending = None
        if self.state == "awaiting_confirmation":
            self.transition_to("idle")

    def has_active_pending(self) -> bool:
        return self.pending is not None and not self.pending.is_expired()

    # ─── 整体重置 ─────────────────────────────────────────────────

    def reset(self) -> None:
        self.dialog_history.clear()
        self.intent_history.clear()
        self.round_count = 0
        self.pending = None
        self.state = "idle"

    def is_over_limit(self, max_rounds: int) -> bool:
        return self.round_count > max_rounds


__all__ = [
    "Session",
    "PendingIntent",
    "SessionState",
    "DEFAULT_PENDING_TTL_SECONDS",
    "DEFAULT_DIALOG_HISTORY_MAX_MESSAGES",
]
