"""主线（threads）路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.day import DayResponse
from app.schemas.thread import ThreadCreate, ThreadStepCreate, ThreadUpdate
from app.services import threads as threads_service

router = APIRouter(prefix="/api", tags=["threads"], dependencies=[Depends(rate_limit)])


@router.post("/threads", response_model=DayResponse, status_code=201)
async def create_thread(data: ThreadCreate, db: DatabaseDep) -> DayResponse:
    """开启主线。"""
    return await threads_service.create_thread(db, data.model_dump(exclude_unset=True))


@router.patch("/threads/{thread_id}", response_model=DayResponse)
async def update_thread(
    thread_id: int, data: ThreadUpdate, db: DatabaseDep
) -> DayResponse:
    """更新主线（改名/完成标准/暂停恢复/今天主推/项目）。"""
    return await threads_service.update_thread(
        db, thread_id, data.model_dump(exclude_unset=True)
    )


@router.post("/threads/{thread_id}/steps", response_model=DayResponse)
async def create_thread_step(
    thread_id: int, data: ThreadStepCreate, db: DatabaseDep
) -> DayResponse:
    """写下今天这一步。"""
    return await threads_service.create_thread_step(
        db, thread_id, data.model_dump(exclude_unset=True)
    )
