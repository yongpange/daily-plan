from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.core.time import utc_now


class UsageRecord(BaseModel):
    """一次模型调用的 Token 用量记录。"""

    model_config = ConfigDict(frozen=True)

    feature: str  # 功能域，如 "chat" / "image"
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    created_at: str = Field(default_factory=utc_now)


class UsageRecorder(Protocol):
    """Token 统计扩展点。默认进程内实现，接入数据库/上报时替换。"""

    async def record(self, usage: UsageRecord) -> None: ...

    async def totals(self, feature: str | None = None) -> dict[str, int]: ...


class InMemoryUsageRecorder:
    def __init__(self, max_records: int = 10000) -> None:
        self._records: list[UsageRecord] = []
        self._max = max_records

    async def record(self, usage: UsageRecord) -> None:
        self._records.append(usage)
        overflow = len(self._records) - self._max
        if overflow > 0:
            del self._records[:overflow]

    async def totals(self, feature: str | None = None) -> dict[str, int]:
        records = [
            usage for usage in self._records if feature is None or usage.feature == feature
        ]
        return {
            "requests": len(records),
            "prompt_tokens": sum(usage.prompt_tokens for usage in records),
            "completion_tokens": sum(usage.completion_tokens for usage in records),
        }
