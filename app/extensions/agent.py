from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel


class AgentRunEvent(BaseModel):
    """Agent 执行过程事件（SSE data 负载）。"""

    message: str = ""
    tool_call: str | None = None
    done: bool = False
    error: str | None = None


class AgentRunner(Protocol):
    """Agent 调用扩展点。以异步流返回执行过程。"""

    async def run(
        self, goal: str, *, context: dict | None = None
    ) -> AsyncIterator[AgentRunEvent]: ...
