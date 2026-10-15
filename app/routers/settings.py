from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.settings import ProfileOut, SettingsOut, SettingsUpdate
from app.services import settings as settings_service

router = APIRouter(
    prefix="/api", tags=["settings"], dependencies=[Depends(rate_limit)]
)


@router.get("/settings", response_model=SettingsOut)
async def get_settings(db: DatabaseDep) -> SettingsOut:
    return await settings_service.get_settings(db)


@router.patch("/settings", response_model=ProfileOut)
async def update_settings(data: SettingsUpdate, db: DatabaseDep) -> ProfileOut:
    return await settings_service.update_settings(db, data)
