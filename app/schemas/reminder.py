"""提醒（reminders）请求/响应模型。

校验逻辑（空内容、长度、时间格式、状态枚举）全部留在 Database 层，
请求模型只保证类型正确，字段保持宽松以便复刻旧 payload.get 语义。
"""

from pydantic import BaseModel


class ReminderCreate(BaseModel):
    message: str | None = None
    remind_at: str | None = None


class ReminderUpdate(BaseModel):
    message: str | None = None
    remind_at: str | None = None
    status: str | None = None


class ReminderOut(BaseModel):
    id: int
    message: str
    remind_at: str
    status: str
