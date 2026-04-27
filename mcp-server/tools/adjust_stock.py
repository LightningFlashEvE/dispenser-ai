"""调整库存工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def adjust_stock(reagent_code: str, delta_mg: int) -> str:
        """调整药品库存。

        参数:
            reagent_code: 药品编号
            delta_mg: 库存变化量(mg)，正数表示增加，负数表示扣减

        返回:
            调整后的药品库存信息
        """
        try:
            data = await tool.api_patch(
                f"/api/drugs/{reagent_code}/stock",
                json={"delta_mg": delta_mg},
            )
            return (
                f"库存调整成功\n"
                f"药品: {data['reagent_code']} - {data['reagent_name_cn']}\n"
                f"新库存: {data['stock_mg']} mg ({data['stock_mg']/1000:.1f} g)"
            )
        except Exception as e:
            return f"库存调整失败: {e}"
