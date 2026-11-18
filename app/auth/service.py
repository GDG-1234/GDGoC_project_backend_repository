from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import repository
from app.auth.firebase import FirebaseIdentity
from app.auth.models import User
from app.auth.schemas import UserResponse
from app.common.exceptions import EmailNotAllowedException
from app.core.config import Settings


def check_email_allowed(email: str, settings: Settings) -> None:
    """허용 도메인이 설정되어 있으면 그 도메인의 이메일만 받는다. 비어 있으면 모두 허용."""
    if not settings.allowed_email_domains:
        return
    domain = email.rsplit("@", 1)[-1]
    if domain not in settings.allowed_email_domains:
        raise EmailNotAllowedException(email)


def is_admin(user: User, settings: Settings) -> bool:
    return user.email.lower() in settings.admin_emails


async def get_or_create_user(
    session: AsyncSession, identity: FirebaseIdentity, settings: Settings
) -> User:
    """로그인한 사용자를 돌려준다. 처음 로그인하면 저장한다 (= 회원가입)."""
    check_email_allowed(identity.email, settings)

    user = await repository.get_by_firebase_uid(session, identity.uid)
    if user is None:
        new_user = User(
            firebase_uid=identity.uid,
            email=identity.email,
            name=identity.name,
            picture_url=identity.picture_url,
        )
        try:
            return await repository.add(session, new_user)
        except IntegrityError:
            # 같은 사용자의 첫 요청 두 개가 동시에 들어온 경우: 먼저 저장된 쪽을 쓴다.
            await session.rollback()
            user = await repository.get_by_firebase_uid(session, identity.uid)
            if user is None:
                raise
            return user

    # Google 계정의 이름·사진이 바뀌었을 때만 갱신한다.
    if (user.email, user.name, user.picture_url) != (
        identity.email,
        identity.name,
        identity.picture_url,
    ):
        user.email = identity.email
        user.name = identity.name
        user.picture_url = identity.picture_url
        user = await repository.save(session, user)
    return user


async def list_users(session: AsyncSession) -> list[User]:
    return list(await repository.list_all(session))


def to_response(user: User, settings: Settings) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        picture_url=user.picture_url,
        is_admin=is_admin(user, settings),
        created_at=user.created_at,
    )
