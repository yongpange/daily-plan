"""复盘报表（reports）接口的 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel


class ReportDay(BaseModel):
    plan_date: str
    estimate_minutes: int
    actual_seconds: int
    completed_count: int
    total_count: int
    focus_count: int


class ReasonStat(BaseModel):
    reason: str
    count: int
    label: str


class ReportProject(BaseModel):
    project_name: str
    estimate_minutes: int
    actual_seconds: int
    completed_count: int
    total_count: int


class Carryover(BaseModel):
    task_id: int
    title: str
    carry_count: int
    latest_target_date: str | None = None


class FocusStats(BaseModel):
    segment_count: int
    completed_count: int
    actual_seconds: int
    longest_streak: int


class Insight(BaseModel):
    tone: str
    title: str
    body: str


class RoutineReportDay(BaseModel):
    date: str
    status: str


class ReportRoutine(BaseModel):
    id: int
    title: str
    note: str
    estimate_minutes: int
    color: str
    active: bool
    completed_count: int
    applicable_count: int
    streak: int
    days: list[RoutineReportDay]


class ReportOut(BaseModel):
    period: str
    start: str
    end: str
    days: list[ReportDay]
    reasons: list[ReasonStat]
    projects: list[ReportProject]
    carryovers: list[Carryover]
    focus: FocusStats
    insights: list[Insight]
    review: str
    routines: list[ReportRoutine]


class PeriodReviewIn(BaseModel):
    period: str | None = None
    start: str | None = None
    content: str | None = None


class PeriodReviewOut(BaseModel):
    period: str
    start: str
    content: str


class WeekReviewIn(BaseModel):
    start: str | None = None
    content: str | None = None


class WeekReviewOut(BaseModel):
    start: str
    content: str
