from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

from .agent import AgentRunner
from .base import InMemoryUsageRecorder, UsageRecorder
from .llm import LLMProvider
from .mcp import MCPToolRegistry
from .rag import NullRetriever, RAGRetriever

if TYPE_CHECKING:
    from app.core.config import Settings


@dataclass
class Extensions:
    """AI 能力扩展点容器，lifespan 中创建并挂到 app.state.extensions。"""

    usage_recorder: UsageRecorder
    llm: LLMProvider | None = None
    rag: RAGRetriever = field(default_factory=NullRetriever)
    agent: AgentRunner | None = None
    mcp: MCPToolRegistry | None = None


def build_extensions(settings: Settings) -> Extensions:
    """按配置装配扩展点。当前未配置任何外部 AI 服务，全部为空实现。

    接入真实实现时在此根据 settings 构造对应 Provider。
    """
    return Extensions(usage_recorder=InMemoryUsageRecorder())


def get_extensions(request: Request) -> Extensions:
    return request.app.state.extensions
