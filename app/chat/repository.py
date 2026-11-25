from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chat.models import Conversation, DailyUsage, Message


async def create_conversation(session: AsyncSession, user_id: int, title: str) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def list_conversations(session: AsyncSession, user_id: int) -> Sequence[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return result.scalars().all()


async def get_conversation(
    session: AsyncSession, conversation_id: int, user_id: int, *, with_messages: bool = False
) -> Conversation | None:
    """남의 대화는 없는 것으로 본다 (user_id까지 맞아야 찾는다)."""
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if with_messages:
        query = query.options(selectinload(Conversation.messages))
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def delete_conversation(session: AsyncSession, conversation: Conversation) -> None:
    # PostgreSQL은 FK의 ON DELETE CASCADE로 지워지지만, 로컬 SQLite는 FK 검사가 꺼져 있어서
    # 메시지를 직접 먼저 지운다.
    await session.execute(delete(Message).where(Message.conversation_id == conversation.id))
    await session.delete(conversation)
    await session.commit()


async def recent_messages(session: AsyncSession, conversation_id: int, limit: int) -> list[Message]:
    """최근 메시지 limit개를 오래된 것부터 돌려준다 (AI에 넘길 대화 맥락)."""
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


def _upsert(session: AsyncSession):  # noqa: ANN202  dialect별 insert 함수
    """ON CONFLICT를 쓰는 insert. 운영은 PostgreSQL, 테스트·로컬은 SQLite다."""
    if session.get_bind().dialect.name == "postgresql":
        return postgresql_insert
    return sqlite_insert


async def reserve_daily_message(
    session: AsyncSession, user_id: int, day: date, limit: int
) -> int | None:
    """오늘 사용량을 1 올리고 올린 뒤의 값을 돌려준다. 이미 한도면 올리지 않고 None.

    "없으면 1로 넣고, 있으면 한도 미만일 때만 +1"을 SQL 한 번으로 해서,
    동시에 들어온 요청이 같은 남은 한도를 함께 쓰지 못하게 한다.
    """
    if limit <= 0:
        return None
    insert = _upsert(session)
    stmt = (
        insert(DailyUsage)
        .values(user_id=user_id, day=day, count=1)
        .on_conflict_do_update(
            index_elements=[DailyUsage.user_id, DailyUsage.day],
            set_={"count": DailyUsage.count + 1},
            where=DailyUsage.count < limit,
        )
        .returning(DailyUsage.count)
    )
    result = await session.execute(stmt)
    row = result.first()
    await session.commit()
    return row[0] if row else None


async def release_daily_message(session: AsyncSession, user_id: int, day: date) -> None:
    """예약한 사용량 1을 되돌린다 (AI 호출이 실패했을 때)."""
    await session.execute(
        update(DailyUsage)
        .where(DailyUsage.user_id == user_id, DailyUsage.day == day, DailyUsage.count > 0)
        .values(count=DailyUsage.count - 1)
    )
    await session.commit()


async def get_daily_count(session: AsyncSession, user_id: int, day: date) -> int:
    result = await session.execute(
        select(DailyUsage.count).where(DailyUsage.user_id == user_id, DailyUsage.day == day)
    )
    return result.scalar_one_or_none() or 0


async def add_messages(
    session: AsyncSession, conversation: Conversation, messages: list[Message]
) -> list[Message]:
    session.add_all(messages)
    session.add(conversation)
    await session.commit()
    for message in messages:
        await session.refresh(message)
    return messages
