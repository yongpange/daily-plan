from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Request

from .config import Settings, get_settings
from .errors import AppError


@dataclass(frozen=True)
class AuthContext:
    """认证结果。api_key 未配置时本地使用一律放行（authenticated=True）。"""

    client_id: str
    authenticated: bool = True
    via_api_key: bool = False


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def get_auth_context(
    request: Request, settings: Settings = Depends(get_settings)
) -> AuthContext:
    ip = client_ip(request)
    if not settings.api_key:
        return AuthContext(client_id=ip)
    provided = (
        request.headers.get("x-api-key")
        or request.query_params.get("api_key")
        or ""
    )
    if secrets.compare_digest(provided, settings.api_key):
        return AuthContext(client_id=ip, via_api_key=True)
    raise AppError("未授权或凭证已失效", 401)


class SlidingWindowRateLimiter:
    """进程内滑动窗口限流，按 client_id 计数；limit <= 0 表示关闭。"""

    def __init__(self, limit_per_minute: int = 0) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        window = self._hits.setdefault(key, [])
        cutoff = now - 60
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= self.limit:
            raise AppError("请求过于频繁，请稍后再试", 429)
        window.append(now)


def get_rate_limiter(request: Request) -> SlidingWindowRateLimiter:
    return request.app.state.rate_limiter


async def rate_limit(
    request: Request, auth: AuthContext = Depends(get_auth_context)
) -> None:
    get_rate_limiter(request).check(auth.client_id)
