"""今日视图路由：GET /api/day、POST /api/day/save、POST /api/day/close、GET /api/week。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.day import (
    DayCloseIn,
    DayRecord,
    DayResponse,
    DaySaveIn,
    WeekResponse,
)
from app.services import day as day_service

router = APIRouter(prefix="/api", tags=["day"], dependencies=[Depends(rate_limit)])


@router.get("/day", response_model=DayResponse)
async def get_day(db: DatabaseDep, date: str | None = None) -> dict:
    """今日视图；date 缺省今天，非法日期由 db 层抛「日期格式不正确」。"""
    return await day_service.get_day(db, date)


@router.post("/day/save", response_model=DayRecord)
async def save_day(data: DaySaveIn, db: DatabaseDep) -> dict:
    """保存当日 focus/reflection/mood，返回 days 行。"""
    return await day_service.save_day(db, data.model_dump(exclude_unset=True))


@router.post("/day/close", response_model=DayResponse)
async def close_day(data: DayCloseIn, db: DatabaseDep) -> dict:
    """收工：写下各任务去向，返回 get_day(date) 整个对象。"""
    return await day_service.close_day(db, data.model_dump(exclude_unset=True))


@router.get("/week", response_model=WeekResponse)
async def get_week(db: DatabaseDep, date: str | None = None) -> dict:
    """周视图；date 缺省今天，返回周一到周日的聚合。"""
    return await day_service.get_week(db, date)
