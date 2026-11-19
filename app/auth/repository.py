from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User


async def get_by_firebase_uid(session: AsyncSession, firebase_uid: str) -> User | None:
    result = await session.execute(select(User).where(User.firebase_uid == firebase_uid))
    return result.scalar_one_or_none()


async def add(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def save(session: AsyncSession, user: User) -> User:
    await session.commit()
    await session.refresh(user)
    return user


async def list_all(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.id))
    return result.scalars().all()
