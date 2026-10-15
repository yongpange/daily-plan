"""今日视图（day/week）的请求与响应模型。

字段名与形状以 docs/refactor/api-catalog.md 1.1 为准；
完整性/范围校验留在 Database 层（AppError 原文案）。
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.entry import PlanEntry
from app.schemas.routine import RoutineDay
from app.schemas.thread import ThreadDay


class DayImage(BaseModel):
    id: int
    width: int | None = None
    height: int | None = None


class DayRecord(BaseModel):
    plan_date: str
    focus: str = ""
    reflection: str = ""
    mood: int | None = None
    closed_at: str | None = None
    updated_at: str | None = None
    # POST /api/day/save 只返回 days 行（无 images 键），给默认值兜底
    images: list[DayImage] = []


class Reason(BaseModel):
    value: str
    label: str


class ProjectRef(BaseModel):
    id: int
    name: str
    color: str


class ActiveTimer(BaseModel):
    id: int
    # 任务计时无 routine_id 键；必做计时 plan_entry_id 为 null
    plan_entry_id: int | None = None
    routine_id: int | None = None
    start_at: str
    mode: str
    target_seconds: int | None = None
    plan_date: str
    title: str


class Segment(BaseModel):
    id: int
    # 任务段无 routine_id/kind 键，schema 给默认值
    plan_entry_id: int | None = None
    routine_id: int | None = None
    start_at: str
    end_at: str | None = None
    duration_seconds: int | None = None
    mode: str
    target_seconds: int | None = None
    focus_completed: int
    title: str
    project_name: str
    kind: str | None = None


class DayResponse(BaseModel):
    date: str
    day: DayRecord
    entries: list[PlanEntry]
    projects: list[ProjectRef]
    active_timer: ActiveTimer | None = None
    segments: list[Segment]
    reasons: list[Reason]
    routines: list[RoutineDay]
    threads: list[ThreadDay]


class DecisionIn(BaseModel):
    """收工去向选择；完整性校验（缺 entry_id/action 等）留在 db 层。"""

    entry_id: int | None = None
    action: str | None = None
    reason: str | None = None
    note: str | None = None
    target_date: str | None = None
    next_estimate_minutes: int | None = None
    next_step: str | None = None


class DaySaveIn(BaseModel):
    # date 宽松处理：缺失/非法由 db.valid_date 抛「日期格式不正确」
    date: str | None = None
    focus: str = ""
    reflection: str = ""
    mood: int | None = None


class DayCloseIn(BaseModel):
    date: str | None = None
    focus: str = ""
    reflection: str = ""
    mood: int | None = None
    decisions: list[DecisionIn] = []


class WeekDay(BaseModel):
    plan_date: str
    estimate_minutes: int
    completed_count: int
    total_count: int
    actual_seconds: int


class ReasonStat(BaseModel):
    reason: str
    count: int
    label: str


class WeekProject(BaseModel):
    project_name: str
    estimate_minutes: int
    actual_seconds: int


class Carryover(BaseModel):
    task_id: int
    title: str
    carry_count: int
    latest_target_date: str


class WeekResponse(BaseModel):
    start: str
    end: str
    days: list[WeekDay]
    reasons: list[ReasonStat]
    projects: list[WeekProject]
    carryovers: list[Carryover]
    review: str
