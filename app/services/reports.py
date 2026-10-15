"""复盘报表业务逻辑：周期报表查询与周期/周复盘保存。"""

from __future__ import annotations

from datetime import date

from starlette.concurrency import run_in_threadpool

from app.core.database import Database


async def get_report(
    db: Database, plan_date: str | None = None, period: str | None = None
) -> dict:
    """周期报表；plan_date/period 缺省为今天/week，校验在 db 层。"""
    anchor = plan_date or date.today().isoformat()
    value = period or "week"
    return await run_in_threadpool(db.get_report, anchor, value)


async def save_period_review(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.save_period_review, payload)


async def save_week_review(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.save_week_review, payload)
