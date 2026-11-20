from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import CurrentUser, SessionDep, SettingsDep
from app.chat import service
from app.chat.ai_client import AiClient, get_ai_client
from app.chat.schemas import (
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from app.common.schemas import ItemsResponse
from app.programs.dependencies import get_result_store
from app.programs.result_store import ResultStore

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


@router.post(
    "",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
    summary="새 대화 만들기",
)
async def create_conversation(
    body: CreateConversationRequest, user: CurrentUser, session: SessionDep
) -> ConversationSummary:
    return await service.create_conversation(session, user, body.title)


@router.get(
    "",
    response_model=ItemsResponse[ConversationSummary],
    status_code=status.HTTP_200_OK,
    summary="내 대화 목록 (최근 대화부터)",
)
async def list_conversations(
    user: CurrentUser, session: SessionDep
) -> ItemsResponse[ConversationSummary]:
    return ItemsResponse(items=await service.list_conversations(session, user))


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    status_code=status.HTTP_200_OK,
    summary="대화 하나와 메시지 전체",
)
async def read_conversation(
    conversation_id: int, user: CurrentUser, session: SessionDep
) -> ConversationDetail:
    return await service.get_conversation(session, conversation_id, user)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="대화 삭제",
)
async def delete_conversation(conversation_id: int, user: CurrentUser, session: SessionDep) -> None:
    await service.delete_conversation(session, conversation_id, user)


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="메시지 보내기 → AI 답변 (하루 보낼 수 있는 수 제한)",
)
async def send_message(
    conversation_id: int,
    body: SendMessageRequest,
    user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
    ai: Annotated[AiClient, Depends(get_ai_client)],
    store: Annotated[ResultStore, Depends(get_result_store)],
) -> SendMessageResponse:
    return await service.send_message(
        session, conversation_id, user, body.content, ai, store, settings
    )
