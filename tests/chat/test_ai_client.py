import json

import httpx
import pytest

from app.chat.ai_client import ChatTurn, FakeAiClient, HttpAiClient, get_ai_client
from app.core.config import Settings

pytestmark = pytest.mark.anyio

TURNS = [ChatTurn(role="user", content="오늘 점심 뭐야?")]


def client_with(handler: httpx.MockTransport) -> HttpAiClient:
    return HttpAiClient("https://agent.test/", "secret", 5, transport=handler)


async def test_http_client_sends_spec_request_and_reads_reply() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Service-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"reply": "제육볶음이에요.", "resultIds": ["r_1"]})

    reply = await client_with(httpx.MockTransport(handler)).respond(12, TURNS)

    assert seen["url"] == "https://agent.test/agent/respond"
    assert seen["key"] == "secret"
    assert seen["body"] == {
        "conversationId": 12,
        "messages": [{"role": "user", "content": "오늘 점심 뭐야?"}],
    }
    assert (reply.reply, reply.result_ids) == ("제육볶음이에요.", ["r_1"])


async def test_http_client_result_ids_are_optional() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"reply": "네"}))

    reply = await client_with(transport).respond(1, TURNS)

    assert reply.result_ids == []


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, json={}), httpx.Response(200, json={"text": "형식이 다름"})],
)
async def test_http_client_raises_on_error(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda _: response)

    with pytest.raises(Exception):  # noqa: B017  채팅이 어떤 예외든 502로 바꾼다
        await client_with(transport).respond(1, TURNS)


def test_fake_client_when_url_is_empty() -> None:
    assert isinstance(get_ai_client(Settings(ai_service_url="")), FakeAiClient)


def test_http_client_when_url_is_set() -> None:
    client = get_ai_client(Settings(ai_service_url="https://agent.test", ai_service_key="k"))

    assert isinstance(client, HttpAiClient)
