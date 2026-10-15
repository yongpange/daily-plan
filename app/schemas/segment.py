from pydantic import BaseModel


class SegmentListItem(BaseModel):
    """GET /api/segments 列表项（catalog 1.2）。

    entry_id 即 plan_entries.id（db.list_segments_between 的列别名），
    注意不是 plan_entry_id。
    """

    id: int
    start_at: str
    end_at: str | None = None
    duration_seconds: int | None = None
    mode: str
    focus_completed: int | None = None
    entry_id: int
    plan_date: str
    estimate_minutes: int
    planned_start: str | None = None
    title: str
    project_name: str


class TimeSegment(BaseModel):
    """time_segments 全行（PATCH /api/segments/{id} 响应，catalog 1.2）。"""

    id: int
    plan_entry_id: int
    task_id: int
    start_at: str
    end_at: str | None = None
    duration_seconds: int | None = None
    mode: str
    target_seconds: int | None = None
    focus_completed: int
    created_at: str


class SegmentUpdate(BaseModel):
    """PATCH /api/segments/{id} 请求体（校验在 db.update_segment，保持宽松）。"""

    duration_minutes: int | None = None
