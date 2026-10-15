from pydantic import BaseModel

from app.schemas.entry import PlanEntry
from app.schemas.routine import RoutineDay


class TimerStartIn(BaseModel):
    """POST /api/timer/start 请求体。

    entry_id 分支为任务计时；routine_id 有值时等同 POST /api/routines/timer/start，
    委托 routines 域处理（date 仅供该分支使用）。
    """

    entry_id: int | None = None
    routine_id: int | None = None
    date: str | None = None
    mode: str | None = None
    focus_minutes: int | None = None


class TimerStartOut(BaseModel):
    """POST /api/timer/start 响应（catalog 1.2，三种形状并集）。

    - 正常启动：started/stopped_entry_id/stopped_routine_id/already_running/mode/target_seconds
    - 同条目重复启动：无 stopped_routine_id/mode/target_seconds 键，取默认值
    - routine_id 分支（routines 域）：already_running/stopped_entry_id/date/routines，无 started
    """

    started: PlanEntry | None = None
    stopped_entry_id: int | None = None
    stopped_routine_id: int | None = None
    already_running: bool
    mode: str | None = None
    target_seconds: int | None = None
    date: str | None = None
    routines: list[RoutineDay] | None = None


class TimerStopIn(BaseModel):
    """POST /api/timer/stop 请求体：{entry_id?} 或 {routine_id}，可加 target_reached。"""

    entry_id: int | None = None
    routine_id: int | None = None
    target_reached: bool | None = None


class TimerStopOut(BaseModel):
    """POST /api/timer/stop 响应（catalog 1.2，多种形状并集）。

    - 无计时在跑：stopped=false/entry_id=null
    - 停掉必做计时：stopped/entry_id=null/routine_id/duration_seconds/mode/focus_completed
    - 正常停任务计时：stopped/entry_id/duration_seconds/mode/focus_completed
    - routine_id 分支（routines 域）：stopped/duration_seconds/date/routines
    """

    stopped: bool
    entry_id: int | None = None
    duration_seconds: int | None = None
    mode: str | None = None
    focus_completed: bool | None = None
    routine_id: int | None = None
    date: str | None = None
    routines: list[RoutineDay] | None = None
