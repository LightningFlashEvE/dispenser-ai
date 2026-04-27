"""下发 command 到控制层工具"""
import json
from .base import MCPTool


def register(mcp, backend_url):
    tool = MCPTool(mcp, backend_url)

    @mcp.tool()
    async def send_command(command_json: str) -> str:
        """将 command JSON 下发到后级控制程序（C++ 控制层）。

        参数:
            command_json: 完整的 command JSON 字符串（符合 command_schema.json）

        返回:
            下发结果，包含 command_id、task_id、状态信息，或错误信息
        """
        try:
            command = json.loads(command_json)

            result = await tool.api_post("/api/manual/command", json={
                "command_type": command.get("command_type", command.get("intent_type", "dispense")),
                "payload": command.get("payload", command),
                "skip_confirmation": True,
            })

            return (
                f"指令已下发\n"
                f"command_id: {result.get('command_id', '-')}\n"
                f"task_id: {result.get('task_id', '-')}\n"
                f"状态: {result.get('status', '-')}"
            )
        except json.JSONDecodeError as e:
            return f"错误: 输入不是有效 JSON: {e}"
        except Exception as e:
            return f"下发指令失败: {e}"
