"""生成 intent_json 工具 — 自然语言 → intent JSON"""
import json
import httpx
from .base import MCPTool


def register(mcp, backend_url, llm_url: str):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def generate_intent(user_text: str, dialog_history: list[dict] | None = None) -> str:
        """根据用户自然语言描述生成 intent JSON。

        参数:
            user_text: 用户的自然语言描述，如「帮我配 500mg 氯化钠到 2 号工位」
            dialog_history: 可选的对话历史数组，格式 [{role: 'user'|'assistant', content: '...'}]

        返回:
            生成的 intent JSON（符合 intent_schema.json），或错误信息
        """
        try:
            system_prompt = _build_system_prompt()

            if dialog_history:
                messages = [
                    {"role": "system", "content": system_prompt},
                    *dialog_history,
                    {"role": "user", "content": user_text},
                ]
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ]

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{llm_url}/chat/completions",
                    json={
                        "model": "default",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 1024,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            intent = json.loads(content)

            # 基本校验
            if "intent_type" not in intent:
                return "错误: LLM 返回缺少 intent_type 字段"

            return json.dumps(intent, ensure_ascii=False, indent=2)

        except json.JSONDecodeError as e:
            return f"错误: LLM 返回不是有效 JSON: {e}"
        except Exception as e:
            return f"生成 intent 失败: {e}"


def _build_system_prompt() -> str:
    return """你是一个配药系统的意图解析助手。根据用户的自然语言描述，输出符合以下 schema 的 intent JSON：

{
  "intent_type": "dispense|aliquot|mix|query_stock|restock|device_status|cancel|emergency_stop|formula",
  "target_mass_mg": 目标质量(mg整数)，可选,
  "reagent_name": "药品名称",
  "reagent_code": "药品编号",
  "station_id": "工位编号",
  "tolerance_mg": 容差(mg)，可选,
  "portions": 分装份数，仅aliquot,
  "components": 混合组分列表，仅mix,
  "is_complete": true|false,
  "clarification_question": "信息不足时的反问",
}

约束:
- 质量单位统一为 mg 整数
- 如果用户信息不完整，设置 is_complete=false 并提出 clarification_question
- 不要输出 JSON 以外的任何内容"""
