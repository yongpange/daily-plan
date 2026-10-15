"""感悟库路由：感悟 CRUD、阅读计数、来源列表、模板与标签建议。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import DatabaseDep
from app.core.security import rate_limit
from app.schemas.memo import (
    DeletedOut,
    MemoCreate,
    MemoListItem,
    MemoOut,
    MemoReadIn,
    MemoReadOut,
    MemoSource,
    MemoUpdate,
    TagSuggestion,
    TemplateCreate,
    TemplateOut,
)
from app.services import memos as memos_service

router = APIRouter(prefix="/api", tags=["memos"], dependencies=[Depends(rate_limit)])


@router.get("/memos", response_model=list[MemoListItem])
async def list_memos(
    db: DatabaseDep,
    query: str | None = None,
    date: str | None = None,
    limit: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    task_id: str | None = None,
) -> list[dict]:
    return await memos_service.list_memos(
        db,
        query=query,
        memo_date=date,
        limit=limit,
        source_kind=source_kind,
        source_id=source_id,
        task_id=task_id,
    )


@router.post("/memos", response_model=MemoOut, status_code=201)
async def create_memo(db: DatabaseDep, data: MemoCreate) -> dict:
    return await memos_service.create_memo(db, data.model_dump(exclude_unset=True))


@router.patch("/memos/{memo_id}", response_model=MemoOut)
async def update_memo(memo_id: int, db: DatabaseDep, data: MemoUpdate) -> dict:
    return await memos_service.update_memo(
        db, memo_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/memos/{memo_id}", response_model=DeletedOut)
async def delete_memo(memo_id: int, db: DatabaseDep) -> dict:
    await memos_service.delete_memo(db, memo_id)
    return {"deleted": True}


@router.post("/memo-reads", response_model=MemoReadOut)
async def mark_memo_read(db: DatabaseDep, data: MemoReadIn) -> dict:
    return await memos_service.mark_memo_read(db, data.model_dump(exclude_unset=True))


@router.get("/memo-sources", response_model=list[MemoSource])
async def list_memo_sources(db: DatabaseDep) -> list[dict]:
    return await memos_service.list_memo_sources(db)


@router.get("/memo-templates", response_model=list[TemplateOut])
async def list_memo_templates(db: DatabaseDep) -> list[dict]:
    return await memos_service.list_memo_templates(db)


@router.post("/memo-templates", response_model=TemplateOut, status_code=201)
async def create_memo_template(db: DatabaseDep, data: TemplateCreate) -> dict:
    return await memos_service.create_memo_template(
        db, data.model_dump(exclude_unset=True)
    )


@router.patch("/memo-templates/{template_id}", response_model=TemplateOut)
async def update_memo_template(
    template_id: int, db: DatabaseDep, data: TemplateCreate
) -> dict:
    return await memos_service.update_memo_template(
        db, template_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/memo-templates/{template_id}", response_model=DeletedOut)
async def delete_memo_template(template_id: int, db: DatabaseDep) -> dict:
    await memos_service.delete_memo_template(db, template_id)
    return {"deleted": True}


@router.get("/tags/suggested", response_model=TagSuggestion)
async def suggested_tags(db: DatabaseDep) -> dict:
    return {"tags": await memos_service.suggested_tags(db)}
