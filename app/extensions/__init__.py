"""AI 能力扩展点。

后续接入大模型生图、Token 统计、RAG、Agent、MCP 时：
1. 在对应模块实现协议（LLMProvider / RAGRetriever / AgentRunner / MCPToolRegistry）；
2. 在 registry.build_extensions 中按 Settings 装配真实实现；
3. 路由与业务层通过 Depends 取用，不感知具体实现。
"""

from .base import UsageRecord, UsageRecorder, InMemoryUsageRecorder
from .llm import (
    ChatMessage,
    ChatRequest,
    ChatStreamEvent,
    ImageGenerateRequest,
    ImageStreamEvent,
    LLMProvider,
)
from .rag import RetrievedChunk, RAGRetriever, NullRetriever
from .agent import AgentRunEvent, AgentRunner
from .mcp import MCPTool, MCPToolRegistry
from .registry import Extensions, build_extensions

__all__ = [
    "UsageRecord",
    "UsageRecorder",
    "InMemoryUsageRecorder",
    "ChatMessage",
    "ChatRequest",
    "ChatStreamEvent",
    "ImageGenerateRequest",
    "ImageStreamEvent",
    "LLMProvider",
    "RetrievedChunk",
    "RAGRetriever",
    "NullRetriever",
    "AgentRunEvent",
    "AgentRunner",
    "MCPTool",
    "MCPToolRegistry",
    "Extensions",
    "build_extensions",
]
