"""查询工位状态工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_stations(
        occupied_only: bool = False,
        free_only: bool = False,
    ) -> str:
        """查询工位占用情况和状态。

        参数:
            occupied_only: 仅显示已占用的工位
            free_only: 仅显示空闲的工位

        返回:
            工位列表，包含占用状态、存放的药品信息、位置坐标
        """
        try:
            if free_only:
                data = await tool.api_get("/api/stations/free")
            else:
                params = {}
                if occupied_only:
                    params["occupied_only"] = True
                data = await tool.api_get("/api/stations", params=params)

            if not data:
                if free_only:
                    return "没有空闲工位"
                if occupied_only:
                    return "所有工位均空闲"
                return "没有工位数据"

            return _format_list(data)
        except Exception as e:
            return f"查询工位失败: {e}"


def _format_list(stations: list[dict]) -> str:
    parts = []
    for i, s in enumerate(stations, 1):
        occ = "占用" if s.get("is_occupied") else "空闲"
        bottle = "有瓶" if s.get("has_bottle") else "无瓶"
        drug = f"{s.get('reagent_name_cn', '-')}({s['reagent_code']})" if s.get("reagent_code") else "-"
        parts.append(
            f"{i}. 工位 {s['station_id']} - {occ} | {bottle} | 药品: {drug} | 坐标: ({s.get('position_x', '-')}, {s.get('position_y', '-')})"
        )
    return "\n".join(parts)
