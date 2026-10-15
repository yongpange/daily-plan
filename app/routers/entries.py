"""计划条目路由：薄路由，只做 解析 → 调 service → 返回。"""

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.entry import (
    DeleteResult,
    EntryCreate,
    EntryMove,
    EntryUpdate,
    MoveResult,
    PlanEntry,
)
from app.services import entries as entries_service

router = APIRouter(
    prefix="/api", tags=["entries"], dependencies=[Depends(rate_limit)]
)


@router.post(
    "/entries", response_model=PlanEntry, status_code=201
)
async def create_entry(data: EntryCreate, db: DatabaseDep) -> PlanEntry:
    entry = await entries_service.create_entry(
        db, data.model_dump(exclude_unset=True)
    )
    return PlanEntry(**entry)


@router.patch("/entries/{entry_id}", response_model=PlanEntry)
async def update_entry(
    entry_id: int, data: EntryUpdate, db: DatabaseDep
) -> PlanEntry:
    entry = await entries_service.update_entry(
        db, entry_id, data.model_dump(exclude_unset=True)
    )
    return PlanEntry(**entry)


@router.delete("/entries/{entry_id}", response_model=DeleteResult)
async def delete_entry(entry_id: int, db: DatabaseDep) -> DeleteResult:
    await entries_service.delete_entry(db, entry_id)
    return DeleteResult(deleted=True)


@router.post("/entries/{entry_id}/move", response_model=MoveResult)
async def move_entry(
    entry_id: int, data: EntryMove, db: DatabaseDep
) -> MoveResult:
    result = await entries_service.move_entry(
        db, entry_id, data.model_dump(exclude_unset=True)
    )
    return MoveResult(**result)
