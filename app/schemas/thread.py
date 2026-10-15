"""主线（threads）相关 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel


class ThreadRecent(BaseModel):
    """主线最近两天的一步（GET /api/day 中 recent 的元素）。"""

    date: str
    title: str
    outcome: str | None


class ThreadDay(BaseModel):
    """GET /api/day 中 threads 列表的元素形状（_threads_for_day）。"""

    id: int
    title: str
    done_when: str
    project_name: str | None
    status: str
    featured: bool
    today_entry_id: int | None
    needs_followup: bool
    note_count: int
    recent: list[ThreadRecent]


class ThreadCreate(BaseModel):
    """POST /api/threads 请求体（开启主线）。"""

    date: str | None = None
    title: str | None = None
    done_when: str | None = None
    step: str | None = None
    project_name: str | None = None
    estimate_minutes: int = 30


class ThreadUpdate(BaseModel):
    """PATCH /api/threads/{thread_id} 请求体（全部可选）。"""

    title: str | None = None
    done_when: str | None = None
    status: str | None = None
    featured: bool | None = None
    project_name: str | None = None
    date: str | None = None


class ThreadStepCreate(BaseModel):
    """POST /api/threads/{thread_id}/steps 请求体（写下今天这一步）。"""

    date: str | None = None
    step: str | None = None
    title: str | None = None
    estimate_minutes: int | None = None
