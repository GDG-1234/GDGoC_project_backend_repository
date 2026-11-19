import secrets
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from app.common.exceptions import UnauthorizedException
from app.core.config import Settings, get_settings
from app.programs.registry import ToolRegistry, default_registry
from app.programs.result_store import MemoryResultStore, ResultStore


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


@lru_cache
def get_result_store() -> ResultStore:
    settings = get_settings()
    return MemoryResultStore(
        ttl_seconds=settings.result_ttl_seconds, max_items=settings.result_store_max_items
    )
