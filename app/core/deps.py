from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.security import AuthContext, get_auth_context
from app.extensions.base import UsageRecorder
from app.extensions.llm import LLMProvider
from app.extensions.registry import Extensions, get_extensions

SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthDep = Annotated[AuthContext, Depends(get_auth_context)]
ExtensionsDep = Annotated[Extensions, Depends(get_extensions)]


def get_db(request: Request) -> "Database":
    """Database 单例（lifespan 中创建）。同步方法，调用方需 run_in_threadpool 包装。"""
    return request.app.state.db


DatabaseDep = Annotated["Database", Depends(get_db)]


def get_usage_recorder(extensions: ExtensionsDep) -> UsageRecorder:
    return extensions.usage_recorder


UsageDep = Annotated[UsageRecorder, Depends(get_usage_recorder)]


def get_llm_provider(extensions: ExtensionsDep) -> LLMProvider | None:
    return extensions.llm


LLMDep = Annotated[LLMProvider | None, Depends(get_llm_provider)]
