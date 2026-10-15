"""计划条目业务逻辑：薄封装 Database，同步调用一律走 run_in_threadpool。"""

from starlette.concurrency import run_in_threadpool

from app.core.database import Database


async def create_entry(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.create_entry, payload)


async def update_entry(db: Database, entry_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_entry, entry_id, payload)


async def delete_entry(db: Database, entry_id: int) -> None:
    await run_in_threadpool(db.delete_entry, entry_id)


async def move_entry(db: Database, entry_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.move_entry, entry_id, payload)
