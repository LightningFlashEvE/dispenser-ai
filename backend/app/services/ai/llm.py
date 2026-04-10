import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
你是一台粉末自动配药设备的操作助手。你的唯一职责是理解操作员的语音指令，并将其转换为结构化 JSON 格式输出。

## 当前工位状态
{STATION_SNAPSHOT}

## 输出规则

1. 只输出 JSON，不输出任何说明文、代码块标记（```）或换行前缀
2. JSON 结构严格按照下方格式，不增减字段
3. 所有质量单位统一转换为毫克（mg）整数：
   - 用户说"50克" → target_mass_mg: 50000
   - 用户说"500毫克" → target_mass_mg: 500
   - 用户说"0.5克" → target_mass_mg: 500
4. 如果用户提供的信息不足以完成任务，将 is_complete 设为 false，在 missing_slots 中列出缺失项，在 clarification_question 中用简洁中文提问
5. reagent_hint.raw_text 填写用户说的原始药品描述，guessed_code 和 guessed_name_cn 按你的理解填写，可以为 null

## 意图类型说明

- dispense_powder：称量一种药品放入容器（需要：药品名、质量、目标容器）
- aliquot_powder：将一种药品分装成 N 等份（需要：药品名、份数、每份质量）
- mix_powder：多种药品按比例混合（需要：各组分名称和占比、总质量）
- query_stock：查询库存，无需其他参数
- query_device_status：查询设备状态，无需其他参数
- save_formula：保存配方，无需其他参数
- cancel_task：取消当前任务，无需其他参数
- emergency_stop：紧急停止，无需其他参数
- unknown：无法理解用户意图时使用

## 输出 JSON 格式

{{
  "schema_version": "1.0",
  "intent_id": "{INTENT_ID}",
  "intent_type": "<意图类型>",
  "timestamp": "{TIMESTAMP}",
  "is_complete": true 或 false,
  "missing_slots": [],
  "clarification_question": null 或 "<中文反问>",
  "reagent_hint": {{
    "raw_text": "<用户说的药品名>",
    "guessed_code": "<猜测编码或null>",
    "guessed_name_cn": "<猜测中文名或null>",
    "guessed_name_formula": "<猜测化学式或null>"
  }},
  "params": {{<见下方各意图的参数结构>}},
  "raw_asr_text": "{RAW_ASR_TEXT}",
  "confidence": 0.0~1.0
}}

## 各意图的 params 结构

dispense_powder:
  {{ "target_mass_mg": <整数或null>, "tolerance_mg": <整数或null>, "target_vessel": "<容器编号或null>" }}

aliquot_powder:
  {{ "portions": <整数或null>, "mass_per_portion_mg": <整数或null>, "tolerance_mg": <整数或null>, "target_vessels": [<容器列表>或null] }}

mix_powder:
  {{
    "total_mass_mg": <整数或null>,
    "ratio_type": "mass_fraction" 或 "molar_fraction" 或 null,
    "components": [ {{ "raw_text": "<组分描述>", "fraction": <0~1的小数或null> }} ],
    "target_vessel": "<容器编号或null>"
  }}

query_stock:
  {{ "raw_text": "<用户描述的药品或null>" }}

其他意图（cancel_task/emergency_stop/query_device_status/save_formula/unknown）:
  {{}}
"""


@dataclass
class IntentResult:
    raw_json: dict[str, Any]
    is_complete: bool
    clarification_question: str | None = None
    error: str | None = None


class DialogSession:
    def __init__(self):
        self.messages: list[dict[str, str]] = []
        self.round_count: int = 0

    def reset(self):
        self.messages = []
        self.round_count = 0

    def add_user_message(self, text: str):
        self.messages.append({"role": "user", "content": text})
        self.round_count += 1

    def add_assistant_message(self, json_str: str):
        self.messages.append({"role": "assistant", "content": json_str})

    def is_over_limit(self) -> bool:
        return self.round_count > settings.dialog_max_rounds


class LLMService:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=60.0,
        )

    def build_system_prompt(
        self,
        station_snapshot: str = "工位状态未知（视觉识别暂不可用），请人工确认药品位置。",
    ) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            STATION_SNAPSHOT=station_snapshot,
            INTENT_ID="",
            TIMESTAMP="",
            RAW_ASR_TEXT="",
        )

    async def process(
        self,
        user_text: str,
        session: DialogSession | None = None,
        intent_id: str | None = None,
        station_snapshot: str = "工位状态未知（视觉识别暂不可用），请人工确认药品位置。",
    ) -> IntentResult:
        if intent_id is None:
            intent_id = f"intent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        timestamp = datetime.now(timezone.utc).isoformat()

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            STATION_SNAPSHOT=station_snapshot,
            INTENT_ID=intent_id,
            TIMESTAMP=timestamp,
            RAW_ASR_TEXT=user_text,
        )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if session and session.messages:
            messages.extend(session.messages)

        messages.append({"role": "user", "content": user_text})

        raw_text = await self._call(messages)

        if session:
            session.add_user_message(user_text)

        parsed = self._parse_json(raw_text)
        if parsed is None:
            retry_text = await self._call(
                messages
                + [{"role": "user", "content": "请只输出 JSON，不要其他文字"}]
            )
            if session:
                session.add_user_message("请只输出 JSON，不要其他文字")
            parsed = self._parse_json(retry_text)
            if parsed is None:
                return IntentResult(
                    raw_json={
                        "schema_version": "1.0",
                        "intent_id": intent_id,
                        "intent_type": "unknown",
                        "timestamp": timestamp,
                        "is_complete": True,
                        "missing_slots": [],
                        "clarification_question": None,
                        "reagent_hint": None,
                        "params": {},
                        "raw_asr_text": user_text,
                        "confidence": 0.0,
                    },
                    is_complete=True,
                    error="LLM 输出无法解析为 JSON",
                )

        if session:
            session.add_assistant_message(raw_text)

        return IntentResult(
            raw_json=parsed,
            is_complete=parsed.get("is_complete", True),
            clarification_question=parsed.get("clarification_question"),
        )

    async def _call(self, messages: list[dict[str, str]]) -> str:
        resp = await self._client.post(
            "/chat/completions",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 512,
                },
                "keep_alive": settings.ollama_keep_alive,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            logger.error("Ollama 响应格式异常: %s, body=%s", e, body)
            raise ValueError(f"Ollama 响应格式异常: {e}") from e

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            return None

    async def close(self):
        await self._client.aclose()


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
