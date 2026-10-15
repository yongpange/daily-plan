from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class MCPTool(BaseModel):
    name: str
    description: str = ""


class MCPToolRegistry(Protocol):
    """MCP 工具协议扩展点：列出并调用外部工具。"""

    async def list_tools(self) -> list[MCPTool]: ...

    async def call_tool(self, name: str, arguments: dict) -> dict: ...
