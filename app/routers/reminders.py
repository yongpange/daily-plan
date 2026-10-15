"""提醒路由：解析 → 调 service → 返回。校验在 Database 层。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.reminder import ReminderCreate, ReminderOut, ReminderUpdate
from app.services import reminders as reminders_service

router = APIRouter(
    prefix="/api", tags=["reminders"], dependencies=[Depends(rate_limit)]
)


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(db: DatabaseDep) -> list[dict]:
    return await reminders_service.list_reminders(db)


@router.post("/reminders", response_model=ReminderOut, status_code=201)
async def create_reminder(data: ReminderCreate, db: DatabaseDep) -> dict:
    return await reminders_service.create_reminder(
        db, data.model_dump(exclude_unset=True)
    )


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: int, data: ReminderUpdate, db: DatabaseDep
) -> dict:
    return await reminders_service.update_reminder(
        db, reminder_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, db: DatabaseDep) -> dict:
    await reminders_service.delete_reminder(db, reminder_id)
    return {"deleted": True}
