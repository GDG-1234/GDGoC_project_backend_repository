from collections.abc import AsyncIterator, Callable
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import bearer_scheme, get_identity
from app.auth.firebase import FirebaseIdentity
from app.common.exceptions import UnauthorizedException
from app.core.config import Settings, get_settings
from app.core.database import Base, get_session
from app.main import app

ADMIN_EMAIL = "admin@dgu.ac.kr"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def fake_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> FirebaseIdentity:
    """테스트용 토큰 검증: 토큰 값이 곧 이메일이다. 예: `Bearer alice@dgu.ac.kr`"""
    if credentials is None:
        raise UnauthorizedException()
    email = credentials.credentials
    return FirebaseIdentity(
        uid=f"uid-{email}", email=email, name=email.split("@")[0], picture_url=None
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", admin_emails=[ADMIN_EMAIL])


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    overrides: dict[Callable[..., object], Callable[..., object]] = {
        get_session: override_session,
        get_identity: fake_identity,
        get_settings: lambda: settings,
    }
    app.dependency_overrides.update(overrides)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


def auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {email}"}
