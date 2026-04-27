"""LLM 调用封装 —— llama.cpp server OpenAI 兼容接口。

职责：
- 调用 /v1/chat/completions（含 streaming 模式）
- 按 force_json 分别走 intent / dialog 两套温度
- 解析 JSON 响应
- 不维护 Session（交由 services/dialog/session.py）
- 不维护 prompt 模板（交由 services/ai/prompts.py）

新增接口：
- process_dialog_stream()   — 流式返回 dialog token，供 channels.py 切句后分段 TTS
- interpret_confirmation()  — 判断用户在 awaiting_confirmation 状态下的意图
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

import httpx

from app.core.config import settings
from app.services.ai.prompts import (
    DEFAULT_STATION_SNAPSHOT,
    build_dialog_system_prompt,
    build_intent_from_dialog_system_prompt,
    build_intent_system_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """Intent 阶段结果（force_json=True）。"""

    raw_json: dict[str, Any] | None = None
    is_complete: bool = True
    clarification_question: str | None = None
    error: str | None = None


@dataclass
class DialogResult:
    """Dialog 阶段结果（自然语言）。"""

    text: str = ""
    error: str | None = None


class LLMService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            timeout=httpx.Timeout(settings.llm_request_timeout_sec, connect=5.0, read=30.0, write=5.0, pool=30.0),
            limits=httpx.Limits(
                max_connections=8,
                max_keepalive_connections=4,
                keepalive_expiry=5.0,
            ),
            headers={"Authorization": "Bearer none"},
            trust_env=False,
        )

    # ─── 公共入口 ─────────────────────────────────────────────────

    async def process_intent(
        self,
        user_text: str,
        intent_history: list[dict[str, str]] | None = None,
        intent_id: str | None = None,
        station_snapshot: str = DEFAULT_STATION_SNAPSHOT,
    ) -> IntentResult:
        """意图阶段：强制 JSON 输出。"""
        if intent_id is None:
            intent_id = f"intent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.now(timezone.utc).isoformat()

        system_prompt = build_intent_system_prompt(
            intent_id=intent_id,
            timestamp=timestamp,
            raw_asr_text=user_text,
            station_snapshot=station_snapshot,
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if intent_history:
            messages.extend(intent_history)
        messages.append({"role": "user", "content": user_text})

        try:
            raw_text = await self._call(messages, force_json=True)
        except httpx.HTTPError as e:
            logger.error("LLM 意图调用网络错误 [%s]: %s", type(e).__name__, e)
            return IntentResult(error=f"LLM 服务暂时不可用：{type(e).__name__}")

        parsed = _parse_json(raw_text)
        if parsed is None:
            logger.warning("LLM 首轮输出无法解析为 JSON，触发一次 retry")
            retry_messages = messages + [
                {"role": "assistant", "content": raw_text},
                {"role": "user", "content": "请只输出合法 JSON，不要任何其他文字或代码块标记"},
            ]
            try:
                retry_text = await self._call(retry_messages, force_json=True)
            except httpx.HTTPError as e:
                logger.error("LLM 意图 retry 网络错误 [%s]: %s", type(e).__name__, e)
                return IntentResult(error=f"LLM 服务暂时不可用：{type(e).__name__}")
            parsed = _parse_json(retry_text)
            if parsed is None:
                return IntentResult(error="LLM 输出无法解析为 JSON")

        return IntentResult(
            raw_json=parsed,
            is_complete=parsed.get("is_complete", True),
            clarification_question=parsed.get("clarification_question"),
        )

    async def process_intent_from_dialog(
        self,
        dialog_history: list[dict[str, str]],
        intent_id: str | None = None,
        station_snapshot: str = DEFAULT_STATION_SNAPSHOT,
    ) -> IntentResult:
        """从对话历史解析意图：强制 JSON 输出。"""
        if intent_id is None:
            intent_id = f"intent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.now(timezone.utc).isoformat()

        # 把对话历史格式化为文本
        history_lines: list[str] = []
        for msg in dialog_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                history_lines.append(f"用户：{content}")
            elif role == "assistant":
                history_lines.append(f"AI：{content}")
        dialog_text = "\n".join(history_lines)

        system_prompt = build_intent_from_dialog_system_prompt(
            intent_id=intent_id,
            timestamp=timestamp,
            dialog_history=dialog_text,
            station_snapshot=station_snapshot,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请根据以上对话历史，输出用户的最终意图 JSON。"},
        ]

        try:
            raw_text = await self._call(messages, force_json=True)
        except httpx.HTTPError as e:
            logger.error("LLM 意图调用网络错误 [%s]: %s", type(e).__name__, e)
            return IntentResult(error=f"LLM 服务暂时不可用：{type(e).__name__}")

        parsed = _parse_json(raw_text)
        if parsed is None:
            logger.warning("LLM 首轮输出无法解析为 JSON，触发一次 retry")
            retry_messages = messages + [
                {"role": "assistant", "content": raw_text},
                {"role": "user", "content": "请只输出合法 JSON，不要任何其他文字或代码块标记"},
            ]
            try:
                retry_text = await self._call(retry_messages, force_json=True)
            except httpx.HTTPError as e:
                logger.error("LLM 意图 retry 网络错误 [%s]: %s", type(e).__name__, e)
                return IntentResult(error=f"LLM 服务暂时不可用：{type(e).__name__}")
            parsed = _parse_json(retry_text)
            if parsed is None:
                return IntentResult(error="LLM 输出无法解析为 JSON")

        return IntentResult(
            raw_json=parsed,
            is_complete=parsed.get("is_complete", True),
            clarification_question=parsed.get("clarification_question"),
        )

    async def process_dialog(
        self,
        user_text: str,
        dialog_history: list[dict[str, str]] | None = None,
        station_snapshot: str = DEFAULT_STATION_SNAPSHOT,
    ) -> DialogResult:
        """对话阶段：自然语言输出（完整返回，非流式）。"""
        system_prompt = build_dialog_system_prompt(station_snapshot=station_snapshot)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if dialog_history:
            messages.extend(dialog_history)
        messages.append({"role": "user", "content": user_text})

        try:
            raw_text = await self._call(messages, force_json=False)
        except httpx.HTTPError as e:
            logger.error("LLM 对话调用网络错误 [%s]: %s", type(e).__name__, e)
            return DialogResult(error="LLM 服务暂时不可用，请稍后重试")

        return DialogResult(text=_clean_dialog_text(raw_text))

    async def process_dialog_stream(
        self,
        user_text: str,
        dialog_history: list[dict[str, str]] | None = None,
        station_snapshot: str = DEFAULT_STATION_SNAPSHOT,
    ) -> AsyncIterator[str]:
        """对话阶段流式版：逐 token yield，供调用方切句后分段送 TTS。

        异常时 yield 一个错误提示文本（保证调用方始终能拿到至少一段文字）。
        """
        system_prompt = build_dialog_system_prompt(station_snapshot=station_snapshot)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if dialog_history:
            messages.extend(dialog_history)
        messages.append({"role": "user", "content": user_text})

        body: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "temperature": settings.llm_dialog_temperature,
            "max_tokens": settings.llm_max_tokens,
        }

        _t0 = time.time()
        try:
            async for token in self._call_stream_tokens("/chat/completions", body):
                yield _clean_token(token)
        except httpx.HTTPError as e:
            logger.error("LLM dialog stream 网络错误 [%s]: %s", type(e).__name__, e)
            yield "抱歉，服务暂时不可用，请稍后重试。"
            return
        except Exception as e:
            logger.exception("LLM dialog stream 未知异常: %s", e)
            yield "抱歉，处理时出现错误，请重试。"
            return

        logger.info("LLM process_dialog_stream ok elapsed=%.1fs", time.time() - _t0)

    async def interpret_confirmation(
        self,
        user_text: str,
        pending_summary: str,
    ) -> Literal["confirm", "cancel", "modify", "unrelated"]:
        """判断用户在 awaiting_confirmation 状态下的意图。

        返回值语义：
        - confirm   — 同意执行当前 pending_action
        - cancel    — 拒绝/取消
        - modify    — 想修改参数（重新进入对话）
        - unrelated — 与确认无关（继续普通对话）
        """
        prompt = (
            f"你是配药助手。系统正在等待用户确认以下操作：\n{pending_summary}\n\n"
            f"用户说：\"{user_text}\"\n\n"
            "请只输出一个词（不带任何标点或额外说明）：\n"
            "- confirm  （用户同意执行）\n"
            "- cancel   （用户拒绝/取消）\n"
            "- modify   （用户想修改参数）\n"
            "- unrelated（与确认无关）"
        )
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        body: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "temperature": 0.0,
            "max_tokens": 16,
        }
        try:
            result = await self._call_stream("/chat/completions", body)
            t = result.strip().lower()
            if "confirm" in t:
                return "confirm"
            if "cancel" in t:
                return "cancel"
            if "modify" in t:
                return "modify"
            return "unrelated"
        except Exception as e:
            logger.warning("interpret_confirmation 调用异常: %s — 保守回退 unrelated", e)
            return "unrelated"

    # ─── 底层调用 ─────────────────────────────────────────────────

    async def _call(self, messages: list[dict[str, str]], *, force_json: bool) -> str:
        """统一走 stream 模式，复用全局 httpx.AsyncClient。"""
        body: dict[str, Any] = {
            "messages": messages,
            "stream": True,
            "temperature": (
                settings.llm_intent_temperature if force_json else settings.llm_dialog_temperature
            ),
            "max_tokens": settings.llm_max_tokens,
        }
        if force_json:
            body["response_format"] = {"type": "json_object"}

        _t0 = time.time()
        content = await self._call_stream("/chat/completions", body)
        est_tokens = max(1, int(len(content) / 2.5))
        logger.info(
            "LLM _call ok force_json=%s elapsed=%.1fs content_len=%d est_tokens=%d",
            force_json, time.time() - _t0, len(content), est_tokens,
        )
        return content

    async def _call_stream(self, path: str, body: dict[str, Any]) -> str:
        """流式读取 SSE 响应，累积 delta.content 并返回完整内容。"""
        async with self._client.stream("POST", path, json=body) as resp:
            resp.raise_for_status()
            full_content = ""
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    full_content += delta
            return full_content

    async def _call_stream_tokens(
        self, path: str, body: dict[str, Any]
    ) -> AsyncIterator[str]:
        """流式读取 SSE 响应，逐 token yield delta.content。"""
        async with self._client.stream("POST", path, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    return
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = (
                    chunk.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    yield delta

    async def close(self) -> None:
        await self._client.aclose()


def _clean_token(token: str) -> str:
    return token


def _parse_json(text: str) -> dict | None:
    """容错解析，兼容偶尔出现的 ```json``` 代码块。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 1)[1]
        if t.startswith("json"):
            t = t[4:]
        t = t.split("```", 1)[0].strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(t[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _clean_dialog_text(text: str) -> str:
    import re
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.strip().split("\n"):
        stripped = raw.strip()
        if re.match(r"^-?\d+$", stripped):
            continue
        if re.match(r"^-?\d+[a-z]", stripped) and len(stripped) < 20:
            continue
        if ".ggml" in stripped or ".bin" in stripped:
            continue
        lines.append(raw)
    result = "\n".join(lines).strip()
    return result or text.strip()


# ─── 单例 ─────────────────────────────────────────────────────────

_llm_instance: LLMService | None = None
_llm_lock: asyncio.Lock | None = None


def _get_llm_lock() -> asyncio.Lock:
    global _llm_lock
    if _llm_lock is None:
        _llm_lock = asyncio.Lock()
    return _llm_lock


async def get_llm_async() -> LLMService:
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    async with _get_llm_lock():
        if _llm_instance is None:
            _llm_instance = LLMService()
    return _llm_instance


def get_llm() -> LLMService:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance


__all__ = [
    "LLMService",
    "IntentResult",
    "DialogResult",
    "get_llm",
    "get_llm_async",
    "_clean_dialog_text",
]
