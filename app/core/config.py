from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"


class Settings(BaseSettings):
    """服务配置。可用环境变量覆盖，前缀 DAILY_PLAN_（如 DAILY_PLAN_PORT）。"""

    model_config = SettingsConfigDict(
        env_prefix="DAILY_PLAN_",
        env_file=ROOT / ".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8765
    data_dir: Path = DATA_DIR
    web_dir: Path = WEB_DIR

    # 认证：本地单人使用时留空；设置后所有 /api 请求需带 X-API-Key。
    api_key: str | None = None
    # 限流：单 IP 每分钟请求数，0 表示关闭。
    rate_limit_per_minute: int = 0
    cors_origins: list[str] = [
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ]
    log_file: Path = DATA_DIR / "daily_plan.log"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "daily_plan.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()
