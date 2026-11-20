from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.chat.ai_client import AiReply, ChatTurn, get_ai_client
from app.core.config import Settings
from app.main import app
from app.programs.dependencies import get_result_store
from app.programs.result_store import MemoryResultStore
from tests.conftest import auth

pytestmark = pytest.mark.anyio

ALICE = auth("alice@dgu.ac.kr")
BOB = auth("bob@dgu.ac.kr")


class RecordingAi:
    """받은 대화를 기록하고, 정해 둔 답변과 skill 결과 ID를 돌려주는 가짜 AI."""

    def __init__(self) -> None:
        self.calls: list[list[ChatTurn]] = []
        self.result_ids: list[str] = []
        self.fail = False

    async def respond(self, conversation_id: int, messages: list[ChatTurn]) -> AiReply:
        if self.fail:
            raise RuntimeError("AI down")
        self.calls.append(messages)
        return AiReply(reply=f"답변 {len(self.calls)}", result_ids=self.result_ids)


@pytest.fixture
def ai() -> RecordingAi:
    return RecordingAi()


@pytest.fixture
def store() -> MemoryResultStore:
    return MemoryResultStore(ttl_seconds=60, max_items=10)


@pytest.fixture(autouse=True)
def chat_overrides(
    client: AsyncClient, ai: RecordingAi, store: MemoryResultStore
) -> Iterator[None]:
    # client 픽스처가 먼저 만들어진 뒤에 덮어써야 지워지지 않는다.
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_result_store] = lambda: store
    yield


async def new_conversation(client: AsyncClient, headers: dict[str, str] = ALICE) -> int:
    response = await client.post("/api/v1/conversations", json={}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


async def test_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/v1/conversations")

    assert response.status_code == 401


async def test_create_and_list_conversations(client: AsyncClient) -> None:
    first = await new_conversation(client)
    second = await new_conversation(client)

    response = await client.get("/api/v1/conversations", headers=ALICE)

    assert response.status_code == 200
    items = response.json()["items"]
    assert [c["id"] for c in items] == [second, first]
    assert items[0]["title"] == "새 대화"
    assert {"createdAt", "updatedAt"} <= items[0].keys()


async def test_send_message_saves_both_and_sets_title(client: AsyncClient, ai: RecordingAi) -> None:
    conversation_id = await new_conversation(client)

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "정문에서 중도 어떻게 가?"},
        headers=ALICE,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["userMessage"]["role"] == "user"
    assert body["userMessage"]["content"] == "정문에서 중도 어떻게 가?"
    assert body["assistantMessage"]["role"] == "assistant"
    assert body["assistantMessage"]["content"] == "답변 1"
    assert body["remainingToday"] == 49

    detail = (await client.get(f"/api/v1/conversations/{conversation_id}", headers=ALICE)).json()
    assert detail["title"] == "정문에서 중도 어떻게 가?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


async def test_ai_receives_previous_turns(client: AsyncClient, ai: RecordingAi) -> None:
    conversation_id = await new_conversation(client)
    url = f"/api/v1/conversations/{conversation_id}/messages"

    await client.post(url, json={"content": "첫 질문"}, headers=ALICE)
    await client.post(url, json={"content": "두 번째 질문"}, headers=ALICE)

    last_call = ai.calls[-1]
    assert [(t.role, t.content) for t in last_call] == [
        ("user", "첫 질문"),
        ("assistant", "답변 1"),
        ("user", "두 번째 질문"),
    ]


async def test_history_is_limited(client: AsyncClient, ai: RecordingAi, settings: Settings) -> None:
    settings.chat_history_limit = 3
    conversation_id = await new_conversation(client)
    url = f"/api/v1/conversations/{conversation_id}/messages"

    for i in range(3):
        await client.post(url, json={"content": f"질문 {i}"}, headers=ALICE)

    assert len(ai.calls[-1]) == 3
    assert ai.calls[-1][-1].content == "질문 2"


async def test_skill_results_are_saved_as_cards(
    client: AsyncClient, ai: RecordingAi, store: MemoryResultStore
) -> None:
    result_id = await store.put("navigation_find_route", {"segments": [1, 2]})
    ai.result_ids = [result_id, "r_missing"]
    conversation_id = await new_conversation(client)

    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "길 알려줘"},
        headers=ALICE,
    )

    detail = (await client.get(f"/api/v1/conversations/{conversation_id}", headers=ALICE)).json()
    cards = detail["messages"][1]["cards"]
    assert cards == [{"toolName": "navigation_find_route", "ui": {"segments": [1, 2]}}]


async def test_cannot_see_or_use_other_users_conversation(client: AsyncClient) -> None:
    conversation_id = await new_conversation(client, ALICE)

    read = await client.get(f"/api/v1/conversations/{conversation_id}", headers=BOB)
    send = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "hi"}, headers=BOB
    )
    delete = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=BOB)
    listed = await client.get("/api/v1/conversations", headers=BOB)

    assert read.status_code == send.status_code == delete.status_code == 404
    assert read.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert listed.json()["items"] == []


async def test_delete_conversation_removes_messages(client: AsyncClient) -> None:
    conversation_id = await new_conversation(client)
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "hi"}, headers=ALICE
    )

    deleted = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=ALICE)
    after = await client.get(f"/api/v1/conversations/{conversation_id}", headers=ALICE)

    assert deleted.status_code == 204
    assert after.status_code == 404


async def test_daily_limit(client: AsyncClient, settings: Settings) -> None:
    settings.daily_message_limit = 2
    conversation_id = await new_conversation(client)
    url = f"/api/v1/conversations/{conversation_id}/messages"

    first = await client.post(url, json={"content": "1"}, headers=ALICE)
    second = await client.post(url, json={"content": "2"}, headers=ALICE)
    third = await client.post(url, json={"content": "3"}, headers=ALICE)
    other_user = await client.post(
        f"/api/v1/conversations/{await new_conversation(client, BOB)}/messages",
        json={"content": "1"},
        headers=BOB,
    )

    assert first.json()["remainingToday"] == 1
    assert second.json()["remainingToday"] == 0
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "DAILY_LIMIT_EXCEEDED"
    assert other_user.status_code == 201


async def test_ai_failure_returns_502_and_saves_nothing(
    client: AsyncClient, ai: RecordingAi
) -> None:
    ai.fail = True
    conversation_id = await new_conversation(client)

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": "hi"}, headers=ALICE
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"
    detail = (await client.get(f"/api/v1/conversations/{conversation_id}", headers=ALICE)).json()
    assert detail["messages"] == []


async def test_empty_message_is_rejected(client: AsyncClient) -> None:
    conversation_id = await new_conversation(client)

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages", json={"content": ""}, headers=ALICE
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
