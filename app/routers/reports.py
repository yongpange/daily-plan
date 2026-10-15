# app/routers/reports.py
from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.report import (
    PeriodReviewIn,
    PeriodReviewOut,
    ReportOut,
    WeekReviewIn,
    WeekReviewOut,
)
from app.services import reports as reports_service

router = APIRouter(prefix="/api", tags=["reports"], dependencies=[Depends(rate_limit)])


@router.get("/report", response_model=ReportOut)
async def get_report(
    db: DatabaseDep, date: str | None = None, period: str | None = None
) -> ReportOut:
    return await reports_service.get_report(db, plan_date=date, period=period)


@router.post("/review", response_model=PeriodReviewOut)
async def save_review(
    payload: PeriodReviewIn, db: DatabaseDep
) -> PeriodReviewOut:
    data = payload.model_dump(exclude_unset=True)
    return await reports_service.save_period_review(db, data)


@router.post("/week/review", response_model=WeekReviewOut)
async def save_week_review(
    payload: WeekReviewIn, db: DatabaseDep
) -> WeekReviewOut:
    data = payload.model_dump(exclude_unset=True)
    return await reports_service.save_week_review(db, data)
