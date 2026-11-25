"""AI 서비스 연결부.

`AI_SERVICE_URL`이 있으면 AI 서비스의 `POST /agent/respond`를 부르고(`HttpAiClient`),
비어 있으면 임시 답변(`FakeAiClient`)을 쓴다. 형식은 위키 AI_연동_명세서 2장이다.
"""

from dataclasses import dataclass, field
from typing import Annotated, Protocol

import httpx
from fastapi import Depends
from pydantic import Field

from app.chat.schemas import MessageRole
from app.common.schemas import CamelModel
from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ChatTurn:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class AiReply:
    reply: str
    # skill 결과 ID. 백엔드가 이 ID로 화면용 데이터(ui)를 찾아 메시지에 붙인다.
    result_ids: list[str] = field(default_factory=list)


class AiClient(Protocol):
    async def respond(self, conversation_id: int, messages: list[ChatTurn]) -> AiReply: ...


class FakeAiClient:
    """AI 서비스 연결 전 임시 응답. 받은 메시지를 그대로 돌려준다."""

    async def respond(self, conversation_id: int, messages: list[ChatTurn]) -> AiReply:
        last = messages[-1].content if messages else ""
        return AiReply(reply=f"(AI 연결 전 임시 답변) 받은 메시지: {last}")


class AgentRespondResponse(CamelModel):
    """AI 서비스 응답. 형식이 다르면 검증 오류 → 채팅은 502 AI_UNAVAILABLE."""

    reply: str
    result_ids: list[str] = Field(default_factory=list)


class HttpAiClient:
    """AI 서비스의 POST /agent/respond를 부른다. 실패하면 예외를 던진다 (채팅이 502로 바꾼다)."""

    def __init__(
        self,
        base_url: str,
        service_key: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,  # 테스트용
    ) -> None:
        self._url = base_url.rstrip("/") + "/agent/respond"
        self._headers = {"X-Service-Key": service_key} if service_key else {}
        self._timeout = timeout_seconds
        self._transport = transport

    async def respond(self, conversation_id: int, messages: list[ChatTurn]) -> AiReply:
        payload = {
            "conversationId": conversation_id,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(self._url, json=payload, headers=self._headers)
            response.raise_for_status()
        body = AgentRespondResponse.model_validate(response.json())
        return AiReply(reply=body.reply, result_ids=body.result_ids)


def get_ai_client(settings: Annotated[Settings, Depends(get_settings)]) -> AiClient:
    if settings.ai_service_url.strip():
        return HttpAiClient(
            settings.ai_service_url.strip(), settings.ai_service_key, settings.ai_timeout_seconds
        )
    return FakeAiClient()
