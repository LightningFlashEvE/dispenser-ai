"""查询设备状态工具"""
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def query_device_status() -> str:
        """查询设备当前状态，包括设备运行状态、天平就绪状态、状态机状态、当前任务等。

        返回:
            设备状态的详细信息
        """
        try:
            data = await tool.api_get("/api/device/status")
            return _format_status(data)
        except Exception as e:
            return f"查询设备状态失败: {e}"


def _format_status(data: dict) -> str:
    status_map = {
        "device_status": data.get("device_status", "未知"),
        "balance_ready": "就绪" if data.get("balance_ready") else "未就绪",
        "state_machine": data.get("state_machine_state", "未知"),
        "current_task": data.get("current_task_id") or "无",
        "current_command": data.get("current_command_id") or "无",
    }
    return (
        f"设备状态: {status_map['device_status']}\n"
        f"天平状态: {status_map['balance_ready']}\n"
        f"状态机: {status_map['state_machine']}\n"
        f"当前任务: {status_map['current_task']}\n"
        f"当前指令: {status_map['current_command']}"
    )
