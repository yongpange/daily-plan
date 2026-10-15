"""每日必做业务逻辑：薄封装 Database 的 routines 方法。

校验与 SQL 全部留在 db 层（AppError 原文案），这里只做 run_in_threadpool 异步包装。
start_timer / stop_timer 供 timers 域的 /api/timer/* 必做分支复用。
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool


async def create_routine(db, payload: dict) -> dict:
    return await run_in_threadpool(db.create_routine, payload)


async def update_routine(db, routine_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_routine, routine_id, payload)


async def delete_routine(db, routine_id: int, unlock_token: str | None) -> None:
    await run_in_threadpool(db.delete_routine, routine_id, unlock_token)


async def set_check(db, payload: dict) -> dict:
    return await run_in_threadpool(db.set_routine_check, payload)


async def start_timer(db, payload: dict) -> dict:
    """启动每日必做计时（等同 POST /api/routines/timer/start）。"""
    return await run_in_threadpool(db.start_routine_timer, payload)


async def stop_timer(db, payload: dict) -> dict:
    """停止每日必做计时（等同 POST /api/routines/timer/stop）。"""
    return await run_in_threadpool(db.stop_routine_timer, payload)


async def create_challenge(db) -> dict:
    result = await run_in_threadpool(db.create_routine_challenge)
    # 旧契约只下发题目不下发答案；db 已剥离，这里兜底再剥一次
    result["questions"] = [
        {"prompt": item["prompt"]} for item in result.get("questions", [])
    ]
    return result


async def verify_challenge(db, payload: dict) -> dict:
    return await run_in_threadpool(db.verify_routine_challenge, payload)
