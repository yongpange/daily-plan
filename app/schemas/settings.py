from __future__ import annotations

from pydantic import BaseModel

from app.schemas.routine import PublicRoutine


class ProfileOut(BaseModel):
    display_name: str
    avatar_data: str
    focus_minutes: int
    break_minutes: int


class ProfileIn(BaseModel):
    display_name: str | None = None
    avatar_data: str | None = None
    focus_minutes: int | None = None
    break_minutes: int | None = None


class SettingsUpdate(BaseModel):
    """PATCH /api/settings：支持 {"profile": {...}} 或直接平铺四字段，形状判断在 db 层。"""

    profile: ProfileIn | None = None
    display_name: str | None = None
    avatar_data: str | None = None
    focus_minutes: int | None = None
    break_minutes: int | None = None


class SettingsOut(BaseModel):
    profile: ProfileOut
    routines: list[PublicRoutine]
