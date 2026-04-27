"""查询药品库存工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_drug_stock(
        keyword: str | None = None,
        reagent_code: str | None = None,
    ) -> str:
        """查询药品库存信息。

        参数:
            keyword: 药品名称、编号或别名（模糊搜索）
            reagent_code: 药品编号（精确查询，优先级高于 keyword）

        返回:
            药品的编号、名称、位置、库存量(mg)、纯度等信息
        """
        if reagent_code:
            try:
                data = await tool.api_get(f"/api/drugs/{reagent_code}")
                return _format_single(data)
            except Exception as e:
                return f"查询失败: {e}"
        elif keyword:
            try:
                data = await tool.api_get("/api/drugs/search", params={"q": keyword, "limit": 10})
                if not data:
                    return f"未找到与「{keyword}」匹配的药品"
                return _format_list(data)
            except Exception as e:
                return f"查询失败: {e}"
        else:
            try:
                data = await tool.api_get("/api/drugs", params={"active_only": True, "limit": 50})
                return _format_list(data)
            except Exception as e:
                return f"查询失败: {e}"


def _format_single(drug: dict) -> str:
    lines = [
        f"药品编号: {drug['reagent_code']}",
        f"中文名称: {drug['reagent_name_cn']}",
        f"英文名称: {drug.get('reagent_name_en', '-')}",
        f"化学式: {drug.get('reagent_name_formula', '-')}",
        f"纯度等级: {drug.get('purity_grade', '-')}",
        f"CAS号: {drug.get('cas_number', '-')}",
        f"工位: {drug.get('station_id', '-')}",
        f"库存: {drug['stock_mg']} mg ({drug['stock_mg']/1000:.1f} g)",
    ]
    if drug.get('notes'):
        lines.append(f"备注: {drug['notes']}")
    return "\n".join(lines)


def _format_list(drugs: list[dict]) -> str:
    if not drugs:
        return "未找到药品"
    parts = []
    for i, d in enumerate(drugs, 1):
        score = d.get("score")
        score_str = f" (匹配度: {score:.0%})" if score else ""
        parts.append(
            f"{i}. {d['reagent_code']} - {d['reagent_name_cn']}"
            f"{score_str} | 库存: {d['stock_mg']} mg | 工位: {d.get('station_id', '-')}"
        )
    return "\n".join(parts)
