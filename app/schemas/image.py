"""图片（note_images）接口契约模型。"""

from pydantic import BaseModel


class ImageCreate(BaseModel):
    """POST /api/images 请求体。校验全部留给 db 层（它抛原始中文文案）。"""

    owner_type: str = ""
    owner_key: str = ""
    original: str = ""
    thumbnail: str = ""
    width: int | None = None
    height: int | None = None


class ImageOut(BaseModel):
    """POST /api/images 响应（201）。"""

    id: int
    width: int | None
    height: int | None
    owner_type: str
    owner_key: str


class ImageDeleted(BaseModel):
    """DELETE /api/images/{id} 响应。"""

    deleted: bool
