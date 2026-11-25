import logging
from datetime import UTC, date, datetime, timedelta, timezone

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.chat import repository
from app.chat.ai_client import AiClient, ChatTurn
from app.chat.models import Conversation, Message, utc_now
from app.chat.schemas import (
    Card,
    ConversationDetail,
    ConversationSummary,
    MessageResponse,
    SendMessageResponse,
)
from app.common.exceptions import AppException, NotFoundException
from app.core.config import Settings
from app.programs import service as programs_service
from app.programs.result_store import ResultStore

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "새 대화"
TITLE_FROM_MESSAGE_LENGTH = 30
KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 +9시간


def start_of_today_kst(now: datetime) -> datetime:
    """한국 시간 오늘 0시를 UTC로 돌려준다. 하루 질문 수는 이 시각부터 센다."""
    today = now.astimezone(KST).date()
    return datetime(today.year, today.month, today.day, tzinfo=KST).astimezone(UTC)


def to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        cards=[Card.model_validate(card) for card in message.cards or []],
        created_at=message.created_at,
    )


def to_summary(conversation: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


async def _get_owned(
    session: AsyncSession, conversation_id: int, user: User, *, with_messages: bool = False
) -> Conversation:
    conversation = await repository.get_conversation(
        session, conversation_id, user.id, with_messages=with_messages
    )
    if conversation is None:
        raise NotFoundException("CONVERSATION_NOT_FOUND", "대화를 찾을 수 없습니다.")
    return conversation


async def create_conversation(
    session: AsyncSession, user: User, title: str | None
) -> ConversationSummary:
    conversation = await repository.create_conversation(
        session, user.id, (title or "").strip() or DEFAULT_TITLE
    )
    return to_summary(conversation)


async def list_conversations(session: AsyncSession, user: User) -> list[ConversationSummary]:
    return [to_summary(c) for c in await repository.list_conversations(session, user.id)]


async def get_conversation(
    session: AsyncSession, conversation_id: int, user: User
) -> ConversationDetail:
    conversation = await _get_owned(session, conversation_id, user, with_messages=True)
    return ConversationDetail(
        **to_summary(conversation).model_dump(),
        messages=[to_message_response(m) for m in conversation.messages],
    )


async def delete_conversation(session: AsyncSession, conversation_id: int, user: User) -> None:
    conversation = await _get_owned(session, conversation_id, user)
    await repository.delete_conversation(session, conversation)


def today_kst(now: datetime) -> date:
    return now.astimezone(KST).date()


async def remaining_today(session: AsyncSession, user: User, settings: Settings) -> int:
    used = await repository.get_daily_count(session, user.id, today_kst(utc_now()))
    return max(0, settings.daily_message_limit - used)


async def _collect_cards(store: ResultStore, result_ids: list[str]) -> list[dict]:
    cards = []
    for result_id in result_ids:
        stored = await programs_service.get_ui_result(store, result_id)
        if stored is None:
            logger.warning("skill 결과를 찾지 못했습니다 (만료 또는 다른 서버): %s", result_id)
            continue
        cards.append(Card(tool_name=stored.tool_name, ui=stored.ui).model_dump(by_alias=True))
    return cards


async def send_message(
    session: AsyncSession,
    conversation_id: int,
    user: User,
    content: str,
    ai: AiClient,
    store: ResultStore,
    settings: Settings,
) -> SendMessageResponse:
    conversation = await _get_owned(session, conversation_id, user)

    # AI를 부르기 전에 오늘 사용량을 먼저 1 예약한다 (동시 요청도 한도를 넘지 못함).
    day = today_kst(utc_now())
    used = await repository.reserve_daily_message(
        session, user.id, day, settings.daily_message_limit
    )
    if used is None:
        raise AppException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "DAILY_LIMIT_EXCEEDED",
            f"오늘 보낼 수 있는 메시지({settings.daily_message_limit}개)를 모두 썼습니다.",
        )

    history = await repository.recent_messages(
        session, conversation.id, settings.chat_history_limit - 1
    )
    turns = [ChatTurn(role=m.role, content=m.content) for m in history]  # type: ignore[arg-type]
    turns.append(ChatTurn(role="user", content=content))

    try:
        reply = await ai.respond(conversation.id, turns)
    except Exception as exc:
        await repository.release_daily_message(session, user.id, day)  # 실패한 질문은 세지 않는다
        logger.exception("AI 서비스 호출 실패 (conversation=%s)", conversation.id)
        raise AppException(
            status.HTTP_502_BAD_GATEWAY,
            "AI_UNAVAILABLE",
            "AI 서비스가 응답하지 않습니다. 잠시 후 다시 시도해 주세요.",
        ) from exc

    now = utc_now()
    user_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content=content,
        cards=[],
        created_at=now,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=reply.reply,
        cards=await _collect_cards(store, reply.result_ids),
        created_at=now + timedelta(microseconds=1),
    )
    if conversation.title == DEFAULT_TITLE and not history:
        conversation.title = content.strip()[:TITLE_FROM_MESSAGE_LENGTH]
    conversation.updated_at = now
    await repository.add_messages(session, conversation, [user_message, assistant_message])

    return SendMessageResponse(
        user_message=to_message_response(user_message),
        assistant_message=to_message_response(assistant_message),
        remaining_today=max(0, settings.daily_message_limit - used),
    )
