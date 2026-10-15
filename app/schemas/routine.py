"""每日必做（routines）请求/响应模型。契约见 docs/refactor/api-catalog.md 1.3 / 1.10。

注意：active/completed/locked/is_running 在旧实现里是 Python bool，
线上 JSON 为 true/false（见 server.py `_public_routine` / `_routines_on`），
故此处声明为 bool 以保持线上形状一致。所有校验（长度、范围、token、日期）
留在 db 层，请求模型保持宽松，缺字段时由 db 抛原文案 AppError。
"""

from __future__ import annotations

from pydantic import BaseModel


class RoutineCreate(BaseModel):
    title: str | None = None
    note: str | None = None
    estimate_minutes: int | None = None


class RoutineUpdate(BaseModel):
    title: str | None = None
    note: str | None = None
    estimate_minutes: int | None = None
    unlock_token: str | None = None


class RoutineDelete(BaseModel):
    unlock_token: str | None = None


class RoutineCheckIn(BaseModel):
    routine_id: int | None = None
    date: str | None = None
    completed: bool = False


class RoutineTimerStartIn(BaseModel):
    routine_id: int | None = None
    date: str | None = None


class RoutineTimerStopIn(BaseModel):
    routine_id: int | None = None


class RoutineChallengeVerifyIn(BaseModel):
    id: str | None = None
    answers: list[int] | None = None


class PublicRoutine(BaseModel):
    id: int
    title: str
    note: str
    estimate_minutes: int
    color: str
    created_on: str
    active: bool
    completed: bool
    locked: bool
    feedback_count: int


class RoutineDay(PublicRoutine):
    actual_seconds: int
    is_running: bool
    running_started_at: str | None


class RoutineCheckOut(BaseModel):
    date: str
    routines: list[RoutineDay]


class RoutineTimerStartOut(BaseModel):
    already_running: bool
    stopped_entry_id: int | None
    date: str
    routines: list[RoutineDay]


class RoutineTimerStopOut(BaseModel):
    stopped: bool
    duration_seconds: int
    date: str
    routines: list[RoutineDay]


class ChallengeQuestion(BaseModel):
    prompt: str


class RoutineChallengeOut(BaseModel):
    id: str
    expires_at: str
    questions: list[ChallengeQuestion]


class RoutineChallengeVerifyOut(BaseModel):
    unlocked: bool
    unlock_token: str
    expires_at: str


class RoutineDeletedOut(BaseModel):
    deleted: bool
