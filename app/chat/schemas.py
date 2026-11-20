from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.common.schemas import CamelModel

MessageRole = Literal["user", "assistant"]


class Card(CamelModel):
    """답변과 함께 화면에 보여 줄 skill 결과. 예: 길안내 지도."""

    tool_name: str
    ui: dict[str, Any]


class MessageResponse(CamelModel):
    id: int
    role: MessageRole
    content: str
    cards: list[Card]
    created_at: datetime


class ConversationSummary(CamelModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageResponse]


class CreateConversationRequest(CamelModel):
    title: str | None = Field(default=None, max_length=100)


class SendMessageRequest(CamelModel):
    content: str = Field(min_length=1, max_length=2000)


class SendMessageResponse(CamelModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    remaining_today: int
