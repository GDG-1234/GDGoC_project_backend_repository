import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import UnauthorizedException
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.programs.registry import ToolRegistry, default_registry
from app.programs.result_store import DbResultStore, ResultStore


def verify_service_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_service_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.service_api_key
    if not expected or x_service_key is None:
        raise UnauthorizedException("서비스 키가 올바르지 않습니다.")
    if not secrets.compare_digest(x_service_key.encode(), expected.encode()):
        raise UnauthorizedException("서비스 키가 올바르지 않습니다.")


def get_registry() -> ToolRegistry:
    return default_registry


def get_result_store(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResultStore:
    """ui 보관소. 인스턴스가 여러 대여도 공유되도록 DB를 쓴다 (테스트는 메모리로 바꿔 끼운다)."""
    return DbResultStore(session, ttl_seconds=settings.result_ttl_seconds)
