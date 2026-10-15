from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.segment import SegmentListItem, SegmentUpdate, TimeSegment
from app.schemas.timer import TimerStartIn, TimerStartOut, TimerStopIn, TimerStopOut
from app.services import timers as timers_service

router = APIRouter(prefix="/api", tags=["timers"], dependencies=[Depends(rate_limit)])


@router.post("/timer/start", response_model=TimerStartOut)
async def start_timer(data: TimerStartIn, db: DatabaseDep) -> TimerStartOut:
    result = await timers_service.start_timer(db, data.model_dump(exclude_unset=True))
    return TimerStartOut(**result)


@router.post("/timer/stop", response_model=TimerStopOut)
async def stop_timer(data: TimerStopIn, db: DatabaseDep) -> TimerStopOut:
    result = await timers_service.stop_timer(db, data.model_dump(exclude_unset=True))
    return TimerStopOut(**result)


@router.get("/segments", response_model=list[SegmentListItem])
async def list_segments(
    db: DatabaseDep,
    start: str | None = None,
    end: str | None = None,
) -> list[SegmentListItem]:
    rows = await timers_service.list_segments(db, start, end)
    return [SegmentListItem(**row) for row in rows]


@router.patch("/segments/{segment_id}", response_model=TimeSegment)
async def update_segment(
    segment_id: int,
    db: DatabaseDep,
    data: SegmentUpdate = Body(default_factory=SegmentUpdate),
) -> TimeSegment:
    result = await timers_service.update_segment(
        db, segment_id, data.model_dump(exclude_unset=True)
    )
    return TimeSegment(**result)


@router.delete("/segments/{segment_id}")
async def delete_segment(segment_id: int, db: DatabaseDep) -> dict:
    await timers_service.delete_segment(db, segment_id)
    return {"deleted": True}
