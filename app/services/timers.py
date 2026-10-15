from __future__ import annotations

import asyncio
from datetime import date

from starlette.concurrency import run_in_threadpool

from app.core.database import Database
from app.core.errors import AppError
from app.services import routines as routines_service

# one_running_timer 部分唯一索引在并发启动下会撞 IntegrityError，
# 用模块级锁把 start/stop 系列操作串行化（对齐旧 ThreadingHTTPServer 的单请求时序）。
_timer_lock = asyncio.Lock()


async def start_timer(db: Database, payload: dict) -> dict:
    async with _timer_lock:
        if payload.get("routine_id") not in (None, ""):
            return await routines_service.start_timer(db, payload)
        entry_id = payload.get("entry_id")
        if entry_id is None:
            raise AppError("任务需要填写整数")
        return await run_in_threadpool(
            db.start_timer,
            entry_id,
            payload.get("mode") or "open",
            payload.get("focus_minutes") or 25,
        )


async def stop_timer(db: Database, payload: dict) -> dict:
    async with _timer_lock:
        if payload.get("routine_id") not in (None, ""):
            return await routines_service.stop_timer(db, payload)
        return await run_in_threadpool(
            db.stop_timer,
            payload.get("entry_id"),
            payload.get("target_reached") or False,
        )


async def list_segments(
    db: Database, start: str | None = None, end: str | None = None
) -> list[dict]:
    if start is None:
        start = date.today().isoformat()
    if end is None:
        end = start
    return await run_in_threadpool(db.list_segments_between, start, end)


async def update_segment(db: Database, segment_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_segment, segment_id, payload)


async def delete_segment(db: Database, segment_id: int) -> None:
    await run_in_threadpool(db.delete_segment, segment_id)
