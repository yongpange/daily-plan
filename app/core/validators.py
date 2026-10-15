from __future__ import annotations

from datetime import date, datetime, timedelta

from .errors import AppError
from .time import DATE_FORMAT


def valid_date(value: object, field_name: str = "日期") -> str:
    if not isinstance(value, str):
        raise AppError(f"{field_name}格式不正确")
    try:
        return datetime.strptime(value, DATE_FORMAT).date().isoformat()
    except ValueError as exc:
        raise AppError(f"{field_name}格式不正确") from exc


def valid_remind_at(value: object) -> str:
    if not isinstance(value, str):
        raise AppError("请选择提醒的日期和时间")
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise AppError("请选择提醒的日期和时间") from exc
    return parsed.strftime("%Y-%m-%dT%H:%M")


def as_non_negative_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AppError(f"{field_name}需要填写整数") from exc
    if parsed < 0:
        raise AppError(f"{field_name}不能小于 0")
    return parsed


def period_bounds(anchor: str, period: str) -> tuple[date, date]:
    anchor_date = datetime.strptime(valid_date(anchor), DATE_FORMAT).date()
    if period == "week":
        start = anchor_date - timedelta(days=anchor_date.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        start = anchor_date.replace(day=1)
        next_month = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return start, next_month - timedelta(days=1)
    if period == "quarter":
        start_month = ((anchor_date.month - 1) // 3) * 3 + 1
        start = date(anchor_date.year, start_month, 1)
        next_start = (
            date(anchor_date.year + 1, 1, 1)
            if start_month == 10
            else date(anchor_date.year, start_month + 3, 1)
        )
        return start, next_start - timedelta(days=1)
    raise AppError("复盘周期不正确")
