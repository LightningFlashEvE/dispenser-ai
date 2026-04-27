"""查询系统资源状态工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_system_resources() -> str:
        """查询系统资源使用情况，包括 CPU、内存、GPU、磁盘等。

        返回:
            CPU 使用率、核心数、内存使用/总量(MB)、GPU 使用率、磁盘使用/总量(GB) 等信息
        """
        try:
            data = await tool.api_get("/api/system/resources")
            return _format_resources(data)
        except Exception as e:
            return f"查询系统资源失败: {e}"


def _format_resources(data: dict) -> str:
    cpu = data.get("cpu", {})
    mem = data.get("memory", {})
    gpu = data.get("gpu", {})
    disk = data.get("disk", {})

    lines = [
        "=== 系统资源状态 ===",
        f"CPU: {cpu.get('percent', '-'):.1f}% ({cpu.get('cores', '-')} 核)",
        f"内存: {mem.get('used_mb', '-')} / {mem.get('total_mb', '-')} MB ({mem.get('percent', '-')}%)",
        f"GPU: {gpu.get('percent', '-'):.1f}%",
        f"磁盘: {disk.get('used_gb', '-')} / {disk.get('total_gb', '-')} GB ({disk.get('percent', '-')}%)",
    ]
    return "\n".join(lines)
