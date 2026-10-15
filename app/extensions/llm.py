from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class ChatStreamEvent(BaseModel):
    """对话流式事件（SSE data 负载）。"""

    delta: str = ""
    done: bool = False
    error: str | None = None


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    size: str | None = None


class ImageStreamEvent(BaseModel):
    """生图进度事件（SSE data 负载）。"""

    step: str = ""
    progress: float = 0.0
    image_url: str | None = None
    done: bool = False
    error: str | None = None


class LLMProvider(Protocol):
    """大模型服务扩展点：对话与生图均以异步流返回。"""

    name: str

    async def stream_chat(
        self, messages: list[ChatMessage]
    ) -> AsyncIterator[ChatStreamEvent]: ...

    async def stream_image(
        self, prompt: str, *, size: str | None = None
    ) -> AsyncIterator[ImageStreamEvent]: ...
