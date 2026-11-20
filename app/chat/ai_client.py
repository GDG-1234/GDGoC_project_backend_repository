"""AI 서비스 연결부.

AI 파트의 서비스(`POST /agent/respond`)가 준비되기 전까지는 `FakeAiClient`를 쓴다.
연결할 때는 `AiClient`를 구현한 HTTP 클라이언트를 만들고 `get_ai_client`만 바꾸면 된다.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.chat.schemas import MessageRole


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


def get_ai_client() -> AiClient:
    return FakeAiClient()
