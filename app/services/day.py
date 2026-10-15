"""今日视图业务逻辑：薄封装 Database，全部同步调用走 run_in_threadpool。"""
from __future__ import annotations

from datetime import date

from starlette.concurrency import run_in_threadpool

from app.core.database import Database


def _today() -> str:
    return date.today().isoformat()


async def get_day(db: Database, plan_date: str | None = None) -> dict:
    """GET /api/day；plan_date 为 None 时取今天。供 threads 域复用。"""
    return await run_in_threadpool(db.get_day, plan_date or _today())


async def save_day(db: Database, payload: dict) -> dict:
    """POST /api/day/save：upsert days 行并返回。"""
    return await run_in_threadpool(db.save_day, payload)


async def close_day(db: Database, payload: dict) -> dict:
    """POST /api/day/close：收工，返回 get_day(date) 整个对象。"""
    return await run_in_threadpool(db.close_day, payload)


async def get_week(db: Database, anchor: str | None = None) -> dict:
    """GET /api/week；anchor 为 None 时取今天。"""
    return await run_in_threadpool(db.get_week, anchor or _today())
