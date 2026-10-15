"""每日必做（routines）路由：薄路由，解析 → 调 service → 返回。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.routine import (
    PublicRoutine,
    RoutineChallengeOut,
    RoutineChallengeVerifyIn,
    RoutineChallengeVerifyOut,
    RoutineCheckIn,
    RoutineCheckOut,
    RoutineCreate,
    RoutineDelete,
    RoutineDeletedOut,
    RoutineTimerStartIn,
    RoutineTimerStartOut,
    RoutineTimerStopIn,
    RoutineTimerStopOut,
    RoutineUpdate,
)
from app.services import routines as routines_service

router = APIRouter(
    prefix="/api", tags=["routines"], dependencies=[Depends(rate_limit)]
)


@router.post("/routines", response_model=PublicRoutine, status_code=201)
async def create_routine(data: RoutineCreate, db: DatabaseDep) -> PublicRoutine:
    """新建每日必做（无需答题）。"""
    return await routines_service.create_routine(
        db, data.model_dump(exclude_unset=True)
    )


@router.patch("/routines/{routine_id}", response_model=PublicRoutine)
async def update_routine(
    routine_id: int, data: RoutineUpdate, db: DatabaseDep
) -> PublicRoutine:
    """修改每日必做（需 unlock_token）。"""
    return await routines_service.update_routine(
        db, routine_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/routines/{routine_id}", response_model=RoutineDeletedOut)
async def delete_routine(
    routine_id: int, data: RoutineDelete, db: DatabaseDep
) -> dict:
    """停用每日必做（软删除，需 unlock_token）。"""
    await routines_service.delete_routine(db, routine_id, data.unlock_token)
    return {"deleted": True}


@router.post("/routines/check", response_model=RoutineCheckOut)
async def check_routine(data: RoutineCheckIn, db: DatabaseDep) -> RoutineCheckOut:
    """打卡 / 取消打卡。"""
    return await routines_service.set_check(db, data.model_dump(exclude_unset=True))


@router.post("/routines/timer/start", response_model=RoutineTimerStartOut)
async def start_routine_timer(
    data: RoutineTimerStartIn, db: DatabaseDep
) -> RoutineTimerStartOut:
    """启动每日必做计时。"""
    return await routines_service.start_timer(db, data.model_dump(exclude_unset=True))


@router.post("/routines/timer/stop", response_model=RoutineTimerStopOut)
async def stop_routine_timer(
    data: RoutineTimerStopIn, db: DatabaseDep
) -> RoutineTimerStopOut:
    """停止每日必做计时。"""
    return await routines_service.stop_timer(db, data.model_dump(exclude_unset=True))


@router.post("/routines/challenge", response_model=RoutineChallengeOut)
async def create_routine_challenge(db: DatabaseDep) -> RoutineChallengeOut:
    """生成 3 道四则混合题（10 分钟过期），只下发题目不下发答案。"""
    return await routines_service.create_challenge(db)


@router.post("/routines/challenge/verify", response_model=RoutineChallengeVerifyOut)
async def verify_routine_challenge(
    data: RoutineChallengeVerifyIn, db: DatabaseDep
) -> RoutineChallengeVerifyOut:
    """校验挑战答案，全部答对发放 unlock_token（10 分钟有效）。"""
    return await routines_service.verify_challenge(
        db, data.model_dump(exclude_unset=True)
    )
