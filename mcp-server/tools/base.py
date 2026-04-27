"""工具基类和 HTTP 客户端"""
import httpx
from typing import Any
from mcp.server.fastmcp import FastMCP


class MCPTool:
    """所有 MCP 工具的基类"""

    def __init__(self, mcp: FastMCP, backend_url: str):
        self.mcp = mcp
        self.backend_url = backend_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.backend_url,
            timeout=30.0,
            follow_redirects=True,
        )

    async def api_get(self, path: str, params: dict | None = None) -> Any:
        """发送 GET 请求到后端 API"""
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def api_post(self, path: str, json: dict | None = None) -> Any:
        """发送 POST 请求到后端 API"""
        resp = await self._client.post(path, json=json)
        resp.raise_for_status()
        return resp.json()

    async def api_patch(self, path: str, json: dict | None = None) -> Any:
        """发送 PATCH 请求到后端 API"""
        resp = await self._client.patch(path, json=json)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
