from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.deps import ExtensionsDep, UsageDep
from app.core.security import rate_limit
from app.extensions.llm import (
    ChatRequest,
    ChatStreamEvent,
    ImageGenerateRequest,
    ImageStreamEvent,
)

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(rate_limit)])


def sse_stream(events: AsyncIterator[BaseModel]) -> AsyncIterator[str]:
    """把事件模型流编码为 SSE 帧（data: <json>\n\n）。"""

    async def generate() -> AsyncIterator[str]:
        async for event in events:
            yield f"data: {event.model_dump_json()}\n\n"

    return generate()


async def _chat_not_configured() -> AsyncIterator[ChatStreamEvent]:
    yield ChatStreamEvent(error="尚未配置大模型服务", done=True)


async def _image_not_configured() -> AsyncIterator[ImageStreamEvent]:
    yield ImageStreamEvent(step="unconfigured", error="尚未配置生图服务", done=True)


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest, extensions: ExtensionsDep
) -> StreamingResponse:
    """大模型对话 SSE 流式接口（预留）。provider 未配置时返回单帧错误事件。"""
    provider = extensions.llm
    events = (
        provider.stream_chat(payload.messages)
        if provider is not None
        else _chat_not_configured()
    )
    return StreamingResponse(
        sse_stream(events), media_type="text/event-stream"
    )


@router.post("/images/stream")
async def image_stream(
    payload: ImageGenerateRequest, extensions: ExtensionsDep
) -> StreamingResponse:
    """生图进度 SSE 流式接口（预留）。"""
    provider = extensions.llm
    events = (
        provider.stream_image(payload.prompt, size=payload.size)
        if provider is not None
        else _image_not_configured()
    )
    return StreamingResponse(
        sse_stream(events), media_type="text/event-stream"
    )


@router.get("/usage")
async def usage(recorder: UsageDep, feature: str | None = None) -> dict[str, int]:
    """Token 用量统计（当前记录进程内，接入持久化后语义不变）。"""
    return await recorder.totals(feature)