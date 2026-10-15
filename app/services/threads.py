"""主线（threads）业务逻辑。"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.database import Database
from app.services import day as day_service


async def create_thread(db: Database, payload: dict) -> dict:
    """开启主线，返回当天完整视图。"""
    result = await run_in_threadpool(db.create_thread, payload)
    return await day_service.get_day(db, result.get("date"))


async def update_thread(db: Database, thread_id: int, payload: dict) -> dict:
    """更新主线（名称/完成标准/状态/今天主推/项目），锚点日期缺省今天。"""
    result = await run_in_threadpool(db.update_thread, thread_id, payload)
    return await day_service.get_day(db, result.get("date"))


async def create_thread_step(db: Database, thread_id: int, payload: dict) -> dict:
    """写下今天这一步，返回当天完整视图。"""
    result = await run_in_threadpool(db.create_thread_step, thread_id, payload)
    return await day_service.get_day(db, result.get("date"))
