from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.database import Database
from app.schemas.settings import ProfileOut, SettingsOut, SettingsUpdate


async def get_settings(db: Database) -> SettingsOut:
    data = await run_in_threadpool(db.get_settings)
    return SettingsOut(**data)


async def update_settings(db: Database, data: SettingsUpdate) -> ProfileOut:
    profile = await run_in_threadpool(
        db.save_settings, data.model_dump(exclude_unset=True)
    )
    return ProfileOut(**profile)
