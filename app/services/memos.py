"""感悟库业务逻辑：列表、新建、更新、删除、阅读计数、来源、模板与标签建议。

全部 db 调用经 run_in_threadpool 包装（Database 方法是同步的）。
长度 / 范围 / 枚举等校验留在 db 层（抛 AppError 带原文案）。
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.database import Database
from app.core.errors import AppError


def _optional_int(value: str | None, message: str) -> int | None:
    """查询参数里的整数字符串转 int；空值为 None，非法时报 catalog 约定的 400 文案。"""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise AppError(message) from exc


async def list_memos(
    db: Database,
    *,
    query: str | None = None,
    memo_date: str | None = None,
    limit: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    task_id: str | None = None,
) -> list[dict]:
    if limit is None:
        limit_value = 100
    else:
        try:
            limit_value = int(limit)
        except ValueError as exc:
            raise AppError("数量参数不正确") from exc
    return await run_in_threadpool(
        db.list_memos,
        query or "",
        memo_date,
        limit_value,
        source_kind or "",
        _optional_int(source_id, "感悟来源不正确"),
        _optional_int(task_id, "任务不正确"),
    )


async def create_memo(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.create_memo, payload)


async def update_memo(db: Database, memo_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_memo, memo_id, payload)


async def delete_memo(db: Database, memo_id: int) -> None:
    await run_in_threadpool(db.delete_memo, memo_id)


async def mark_memo_read(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.mark_memo_read, payload)


async def list_memo_sources(db: Database) -> list[dict]:
    return await run_in_threadpool(db.list_memo_sources)


async def list_memo_templates(db: Database) -> list[dict]:
    return await run_in_threadpool(db.list_memo_templates)


async def create_memo_template(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.create_memo_template, payload)


async def update_memo_template(db: Database, template_id: int, payload: dict) -> dict:
    return await run_in_threadpool(db.update_memo_template, template_id, payload)


async def delete_memo_template(db: Database, template_id: int) -> None:
    await run_in_threadpool(db.delete_memo_template, template_id)


async def suggested_tags(db: Database) -> list[str]:
    return await run_in_threadpool(db.suggested_tags)
