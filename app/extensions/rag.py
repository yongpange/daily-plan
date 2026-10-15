from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: str
    content: str
    score: float
    source: str = ""


class RAGRetriever(Protocol):
    """RAG 检索扩展点。实现确定后替换 NullRetriever。"""

    async def add(self, owner_kind: str, owner_key: str, content: str) -> str: ...

    async def search(self, query: str, *, limit: int = 5) -> list[RetrievedChunk]: ...


class NullRetriever:
    """未接入向量库时的空实现：检索恒为空，写入直接丢弃。"""

    async def add(self, owner_kind: str, owner_key: str, content: str) -> str:
        return ""

    async def search(self, query: str, *, limit: int = 5) -> list[RetrievedChunk]:
        return []
