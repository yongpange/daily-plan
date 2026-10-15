"""计划条目（entries）的请求/响应模型。"""

from pydantic import BaseModel


class PlanEntry(BaseModel):
    """`<entry>` 形状（server.py `_entry()` 返回的 dict，字段名固定）。"""

    id: int
    plan_date: str
    estimate_minutes: int
    planned_start: str | None
    sort_order: int
    outcome: str
    unfinished_reason: str | None
    reason_note: str
    target_date: str | None
    thread_id: int | None
    task_id: int
    title: str
    parent_id: int | None
    definition: str
    task_status: str
    project_name: str | None
    thread_title: str | None
    actual_seconds: int
    is_running: int
    has_children: int


class EntryCreate(BaseModel):
    """POST /api/entries 请求体。长度/范围校验在 db 层，这里保持宽松。"""

    date: str | None = None
    title: str | None = None
    project_name: str | None = None
    estimate_minutes: int = 0
    planned_start: str | None = None
    definition: str | None = None
    parent_entry_id: int | str | None = None


class EntryUpdate(BaseModel):
    """PATCH /api/entries/{id} 请求体，全部可选（均可显式置空）。"""

    title: str | None = None
    project_name: str | None = None
    estimate_minutes: int | None = None
    planned_start: str | None = None
    definition: str | None = None
    outcome: str | None = None


class EntryMove(BaseModel):
    """POST /api/entries/{id}/move 请求体。"""

    date: str | None = None


class MoveResult(BaseModel):
    moved_to: str
    title: str
    source_date: str


class DeleteResult(BaseModel):
    deleted: bool
