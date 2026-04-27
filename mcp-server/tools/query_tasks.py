"""查询任务历史工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_tasks(
        status: str | None = None,
        limit: int = 10,
    ) -> str:
        """查询任务历史与执行状态。

        参数:
            status: 按状态过滤，可选值: pending, confirmed, running, completed, failed, cancelled
            limit: 返回数量限制，默认 10

        返回:
            任务列表，包含任务类型、状态、创建时间、执行结果等
        """
        try:
            params = {"limit": min(limit, 200)}
            if status:
                params["status"] = status
            data = await tool.api_get("/api/tasks", params=params)

            if not data:
                return "没有任务记录"

            return _format_list(data)
        except Exception as e:
            return f"查询任务失败: {e}"


def _format_list(tasks: list[dict]) -> str:
    parts = []
    for i, t in enumerate(tasks, 1):
        status_icon = {
            "completed": "✓",
            "failed": "✗",
            "cancelled": "⊘",
            "running": "▶",
            "pending": "◷",
        }.get(t.get("status", ""), "?")

        line = f"{i}. [{status_icon}] {t['task_id'][:8]}... - {t['command_type']} | 状态: {t['status']} | 创建: {t.get('created_at', '-')}"
        if t.get("error_message"):
            line += f"\n   错误: {t['error_message']}"
        parts.append(line)
    return "\n".join(parts)
