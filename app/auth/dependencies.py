from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.firebase import FirebaseIdentity, verify_id_token
from app.auth.models import User
from app.common.exceptions import ForbiddenException, UnauthorizedException
from app.core.config import Settings, get_settings
from app.core.database import get_session

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> FirebaseIdentity:
    """`Authorization: Bearer <Firebase ID 토큰>` 헤더를 검증한다."""
    if credentials is None:
        raise UnauthorizedException()
    return await verify_id_token(credentials.credentials)


async def get_current_user(
    identity: Annotated[FirebaseIdentity, Depends(get_identity)],
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    return await service.get_or_create_user(session, identity, settings)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser, settings: SettingsDep) -> User:
    if not service.is_admin(user, settings):
        raise ForbiddenException("관리자만 사용할 수 있습니다.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
