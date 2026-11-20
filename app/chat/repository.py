from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chat.models import Conversation, Message


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


async def count_user_messages_since(session: AsyncSession, user_id: int, since: datetime) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.user_id == user_id, Message.role == "user", Message.created_at >= since)
    )
    return result.scalar_one()


async def add_messages(
    session: AsyncSession, conversation: Conversation, messages: list[Message]
) -> list[Message]:
    session.add_all(messages)
    session.add(conversation)
    await session.commit()
    for message in messages:
        await session.refresh(message)
    return messages
