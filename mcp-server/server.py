"""MCP Server 入口 — 配药系统工具服务"""
import os
import asyncio
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# 加载环境变量
load_dotenv()

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
LLM_URL = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")

# 创建 MCP Server
mcp = FastMCP(
    "dispenser-ai",
    instructions="配药配料系统 MCP Server，提供药品查询、设备状态查询、任务查询、意图生成、命令下发等工具",
)

# 注册所有工具
from tools import (
    query_drug_stock,
    query_formulas,
    query_device_status,
    query_stations,
    query_tasks,
    query_system_resources,
    generate_intent,
    build_command,
    send_command,
    adjust_stock,
)

query_drug_stock.register(mcp, BACKEND_URL)
query_formulas.register(mcp, BACKEND_URL)
query_device_status.register(mcp, BACKEND_URL)
query_stations.register(mcp, BACKEND_URL)
query_tasks.register(mcp, BACKEND_URL)
query_system_resources.register(mcp, BACKEND_URL)
generate_intent.register(mcp, BACKEND_URL, LLM_URL)
build_command.register(mcp, BACKEND_URL)
send_command.register(mcp, BACKEND_URL)
adjust_stock.register(mcp, BACKEND_URL)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
