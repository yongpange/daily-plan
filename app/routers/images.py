"""图片端点：POST /api/images、GET /api/images/{id}[/thumb]、DELETE /api/images/{id}。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.core.deps import DatabaseDep
from app.core.errors import AppError
from app.core.security import rate_limit
from app.schemas.image import ImageCreate, ImageDeleted, ImageOut
from app.services import images as images_service

router = APIRouter(prefix="/api", tags=["images"], dependencies=[Depends(rate_limit)])


def _image_response(content: bytes, content_type: str) -> Response:
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, no-cache"},
    )


@router.post("/images", response_model=ImageOut, status_code=201)
async def create_image(data: ImageCreate, db: DatabaseDep) -> ImageOut:
    return await images_service.create_image(db, data.model_dump(exclude_unset=True))


@router.get("/images/{image_id}")
async def read_image(image_id: int, db: DatabaseDep) -> Response:
    content, content_type = await images_service.read_image(db, image_id)
    return _image_response(content, content_type)


@router.get("/images/{image_id}/thumb")
async def read_image_thumb(image_id: int, db: DatabaseDep) -> Response:
    content, content_type = await images_service.read_image(db, image_id, thumbnail=True)
    return _image_response(content, content_type)


@router.get("/images/{image_id}/{rest}")
async def read_image_unknown_segment(image_id: int, rest: str) -> Response:
    """旧实现：/thumb 以外的第二段路径 → 404 "没有找到这张图片"。"""
    raise AppError("没有找到这张图片", 404)


@router.delete("/images/{image_id}", response_model=ImageDeleted)
async def delete_image(image_id: int, db: DatabaseDep) -> ImageDeleted:
    await images_service.delete_image(db, image_id)
    return ImageDeleted(deleted=True)
