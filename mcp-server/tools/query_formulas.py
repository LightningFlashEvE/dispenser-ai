"""查询配方工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_formulas(
        keyword: str | None = None,
        formula_id: str | None = None,
    ) -> str:
        """查询配方信息。

        参数:
            keyword: 配方名称、编号或别名（模糊搜索，与 formula_id 二选一）
            formula_id: 配方 ID（精确查询，优先级高于 keyword）

        返回:
            配方列表或详情，包含配方名称、别名、步骤数、各步骤的药品编号、目标质量、容器等
        """
        try:
            if formula_id:
                data = await tool.api_get(f"/api/formulas/{formula_id}")
                return _format_single(data)
            elif keyword:
                data = await tool.api_get("/api/formulas/search", params={"q": keyword, "limit": 10})
                return _format_search(data)
            else:
                data = await tool.api_get("/api/formulas", params={"limit": 50})
                return _format_list(data)
        except Exception as e:
            return f"查询配方失败: {e}"


def _format_single(formula: dict) -> str:
    lines = [
        f"配方ID: {formula['formula_id']}",
        f"名称: {formula['formula_name']}",
        f"别名: {', '.join(formula.get('aliases_list') or []) or '-'}",
        f"备注: {formula.get('notes') or '-'}",
        f"步骤数: {len(formula.get('steps') or [])}",
    ]
    steps = formula.get("steps", [])
    if steps:
        lines.append("--- 步骤明细 ---")
        for s in sorted(steps, key=lambda x: x.get("step_index", 0)):
            reagent = s.get("reagent_code") or "-"
            mass = f"{s['target_mass_mg']}mg" if s.get("target_mass_mg") is not None else "-"
            tol = f"±{s['tolerance_mg']}mg" if s.get("tolerance_mg") is not None else ""
            vessel = s.get("target_vessel") or "-"
            name = s.get("step_name") or ""
            lines.append(
                f"  {s.get('step_index', '?')}. {name} [{s.get('command_type', '-')}] "
                f"{reagent} {mass}{tol} → {vessel}"
            )
    return "\n".join(lines)


def _format_search(formulas: list[dict]) -> str:
    if not formulas:
        return "未找到匹配的配方"
    lines = []
    for f in formulas:
        lines.append(
            f"{f['formula_id']} | {f['formula_name']} "
            f"(别名: {', '.join(f.get('aliases_list') or []) or '-'})"
            f" | {f.get('step_count', 0)} 步骤"
        )
    return "\n".join(lines)


def _format_list(formulas: list[dict]) -> str:
    if not formulas:
        return "暂无配方数据"
    lines = []
    for f in formulas:
        lines.append(
            f"{f['formula_id']} | {f['formula_name']} "
            f"(别名: {', '.join(f.get('aliases_list') or []) or '-'})"
            f" | {len(f.get('steps') or [])} 步骤"
        )
    return "\n".join(lines)
