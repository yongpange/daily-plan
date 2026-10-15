"""图片业务：登记上传、读取字节、删除（文件落盘与校验在 db 层）。"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.database import Database


async def create_image(db: Database, payload: dict) -> dict:
    return await run_in_threadpool(db.create_note_image, payload)


async def read_image(
    db: Database, image_id: int, thumbnail: bool = False
) -> tuple[bytes, str]:
    return await run_in_threadpool(db.read_note_image, image_id, thumbnail)


async def delete_image(db: Database, image_id: int) -> None:
    await run_in_threadpool(db.delete_note_image, image_id)
