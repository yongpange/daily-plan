"""提醒业务逻辑：把同步的 Database 调用包装为 async。"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.database import Database


async def list_reminders(db: Database) -> list[dict]:
    return await run_in_threadpool(db.list_reminders)


async def create_reminder(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.create_reminder, payload)


async def update_reminder(db: Database, reminder_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_reminder, reminder_id, payload)


async def delete_reminder(db: Database, reminder_id: int) -> None:
    await run_in_threadpool(db.delete_reminder, reminder_id)
