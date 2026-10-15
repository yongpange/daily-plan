"""感悟库接口的 Pydantic 请求/响应模型（契约见 docs/refactor/api-catalog.md 1.5）。"""

from __future__ import annotations

from pydantic import BaseModel


class DayImage(BaseModel):
    """感悟 / 每日复盘上挂载的图片摘要（note_images 行）。"""

    id: int
    width: int | None = None
    height: int | None = None


class MemoOut(BaseModel):
    """POST/PATCH /api/memos 响应：memos 全行 + kind + images（无 read 装饰字段）。"""

    id: int
    memo_date: str
    content: str
    tags: str
    pinned: int
    created_at: str
    updated_at: str
    kind: str = "memo"
    images: list[DayImage] = []
    note_title: str
    note_link: str
    source_entry_id: int | None
    source_title: str
    source_estimate_minutes: int | None
    source_actual_seconds: int | None
    source_plan_date: str | None
    source_kind: str
    source_routine_id: int | None
    source_thread_id: int | None
    source_task_id: int | None


class MemoListItem(MemoOut):
    """GET /api/memos 列表元素；daily 复盘元素 id 为日期字符串。"""

    id: int | str
    source_thread_title: str
    read_count: int
    last_read_at: str | None
    read_today: bool


class MemoCreate(BaseModel):
    """POST /api/memos 请求体。长度/来源等校验在 db 层，这里保持宽松。"""

    date: str | None = None
    content: str = ""
    content_format: str | None = None
    tags: str | None = None
    has_images: bool | None = None
    note_title: str | None = None
    note_link: str | None = None
    entry_id: int | None = None
    routine_id: int | None = None
    thread_id: int | None = None


class MemoUpdate(BaseModel):
    """PATCH /api/memos/{id} 请求体（只覆盖传入字段）。"""

    date: str | None = None
    content: str | None = None
    content_format: str | None = None
    tags: str | None = None
    pinned: bool | None = None


class MemoReadIn(BaseModel):
    """POST /api/memo-reads 请求体；memo 时 id 为整数，daily 时为日期字符串。"""

    kind: str = "memo"
    id: int | str | None = None


class MemoReadOut(BaseModel):
    """POST /api/memo-reads 响应。"""

    kind: str
    id: int | str
    read_count: int
    last_read_at: str
    read_today: bool
    counted: bool


class MemoSource(BaseModel):
    """GET /api/memo-sources 元素（主线 / 每日必做来源）。"""

    kind: str
    id: int
    title: str
    count: int
    featured: bool
    active: bool


class TemplateOut(BaseModel):
    """GET/POST/PATCH /api/memo-templates 的模板对象。"""

    id: int
    name: str
    content: str
    updated_at: str


class TemplateCreate(BaseModel):
    """POST /api/memo-templates 请求体（PATCH 复用；内容强制按 rich 清洗在 db 层）。"""

    name: str = ""
    content: str = ""
    content_format: str | None = None


class TagSuggestion(BaseModel):
    """GET /api/tags/suggested 响应。"""

    tags: list[str]


class DeletedOut(BaseModel):
    """DELETE 端点统一响应。"""

    deleted: bool
