"""构建 command JSON 工具 — intent_json → command JSON"""
import json
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def build_command(intent_json: str, drug_info: str | None = None) -> str:
        """将 intent JSON 转换为 command JSON（经过规则引擎校验和药品库补全）。

        参数:
            intent_json: intent JSON 字符串（符合 intent_schema.json）
            drug_info: 可选的药品信息 JSON 字符串，用于补全 command 中的试剂字段

        返回:
            生成的 command JSON（符合 command_schema.json），或错误信息
        """
        try:
            intent = json.loads(intent_json)
            drug = json.loads(drug_info) if drug_info else None

            result = await tool.api_post("/api/manual/command", json={
                "command_type": intent.get("intent_type", "dispense"),
                "payload": _extract_payload(intent, drug),
            })

            return json.dumps(result, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as e:
            return f"错误: 输入不是有效 JSON: {e}"
        except Exception as e:
            return f"构建 command 失败: {e}"


def _extract_payload(intent: dict, drug: dict | None) -> dict:
    """从 intent 中提取 payload 字段"""
    payload = {}

    if intent.get("target_mass_mg") is not None:
        payload["target_mass_mg"] = intent["target_mass_mg"]

    if intent.get("tolerance_mg") is not None:
        payload["tolerance_mg"] = intent["tolerance_mg"]

    if intent.get("station_id"):
        payload["station_id"] = intent["station_id"]

    if intent.get("portions") is not None:
        payload["portions"] = intent["portions"]

    if intent.get("mass_per_portion_mg") is not None:
        payload["mass_per_portion_mg"] = intent["mass_per_portion_mg"]

    if intent.get("components"):
        payload["components"] = intent["components"]

    if intent.get("target_vessel"):
        payload["target_vessel"] = intent["target_vessel"]

    if drug:
        payload.update({
            "reagent_code": drug.get("reagent_code", ""),
            "reagent_name_cn": drug.get("reagent_name_cn", ""),
            "reagent_name_en": drug.get("reagent_name_en", ""),
            "reagent_name_formula": drug.get("reagent_name_formula", ""),
            "purity_grade": drug.get("purity_grade", ""),
            "station_id": drug.get("station_id", payload.get("station_id", "")),
            "molar_weight_g_mol": drug.get("molar_weight_g_mol"),
        })

    return payload
