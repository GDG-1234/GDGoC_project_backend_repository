import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.main import app
from app.programs.dependencies import get_registry, get_result_store
from app.programs.registry import ToolRegistry
from app.programs.result_store import MemoryResultStore
from app.programs.schemas import Candidate, ToolError, ToolNeedClarification, ToolOk

pytestmark = pytest.mark.anyio

KEY = "test-key"
HEADERS = {"X-Service-Key": KEY}

# ---- 테스트용 가짜 tool ----

registry = ToolRegistry()


class EchoInput(BaseModel):
    text: str = Field(description="돌려줄 글자")


class EmptyInput(BaseModel):
    pass


@registry.tool(name="test_echo", description="받은 글자를 돌려준다")
async def echo(args: EchoInput) -> ToolOk:
    return ToolOk(llm={"text": args.text}, ui={"card": args.text})


@registry.tool(name="test_no_ui", description="ui 없이 끝난다")
async def no_ui(args: EmptyInput) -> ToolOk:
    return ToolOk(llm={"done": True})


@registry.tool(name="test_ambiguous", description="후보를 돌려준다")
async def ambiguous(args: EmptyInput) -> ToolNeedClarification:
    return ToolNeedClarification(
        field="cafeteria",
        message="식당이 여러 곳입니다.",
        candidates=[
            Candidate(value="sangrok_3f", label="상록원3층식당"),
            Candidate(value="sangrok_2f", label="상록원2층식당"),
        ],
    )


@registry.tool(name="test_fail", description="예상된 실패")
async def fail(args: EmptyInput) -> ToolOk:
    raise ToolError("MENU_NOT_FOUND", "메뉴가 없습니다.")


@registry.tool(name="test_slow", description="너무 느리다", timeout=0.05)
async def slow(args: EmptyInput) -> ToolOk:
    await asyncio.sleep(1)
    return ToolOk(llm={})


@registry.tool(name="test_crash", description="예상 못 한 예외")
async def crash(args: EmptyInput) -> ToolOk:
    raise RuntimeError("secret internal detail")


@registry.tool(name="test_bad_return", description="잘못된 값을 반환한다")
async def bad_return(args: EmptyInput) -> ToolOk:
    return {"llm": {}}  # type: ignore[return-value]


# ---- 준비: conftest.py의 settings, client를 이 파일에 맞게 바꿔 쓴다 ----


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", service_api_key=KEY)


@pytest.fixture
def store() -> MemoryResultStore:
    return MemoryResultStore(ttl_seconds=60, max_items=10)


@pytest.fixture
async def skills_client(
    client: AsyncClient, store: MemoryResultStore
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_result_store] = lambda: store
    yield client


async def invoke(
    client: AsyncClient, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/skills/{name}/invoke", json={"arguments": arguments or {}}, headers=HEADERS
    )
    assert response.status_code == 200
    return response.json()


# ---- 목록 ----


async def test_list_skills_returns_registered_tools(skills_client: AsyncClient) -> None:
    response = await skills_client.get("/api/v1/skills", headers=HEADERS)

    assert response.status_code == 200
    tools = {t["name"]: t for t in response.json()["items"]}
    assert tools["test_echo"]["description"] == "받은 글자를 돌려준다"
    assert tools["test_echo"]["inputSchema"]["properties"]["text"]["description"] == "돌려줄 글자"


# ---- 인증 ----


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Service-Key": "wrong"}, {"X-Service-Key": "키".encode()}],
    ids=["missing", "wrong", "non-ascii"],
)
async def test_bad_service_key_returns_401(
    skills_client: AsyncClient, headers: dict[str, Any]
) -> None:
    responses = [
        await skills_client.get("/api/v1/skills", headers=headers),
        await skills_client.post(
            "/api/v1/skills/test_echo/invoke", json={"arguments": {}}, headers=headers
        ),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_empty_server_key_rejects_everyone(
    skills_client: AsyncClient, settings: Settings
) -> None:
    settings.service_api_key = ""

    response = await skills_client.get("/api/v1/skills", headers={"X-Service-Key": ""})

    assert response.status_code == 401


# ---- 실행 ----


async def test_unknown_tool_returns_404(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_nothing/invoke", json={"arguments": {}}, headers=HEADERS
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TOOL_NOT_FOUND"


async def test_ok_returns_llm_and_keeps_ui(
    skills_client: AsyncClient, store: MemoryResultStore
) -> None:
    body = await invoke(skills_client, "test_echo", {"text": "안녕"})

    assert body["status"] == "ok"
    assert body["llm"] == {"text": "안녕"}
    assert "ui" not in body
    stored = await store.get(body["resultId"])
    assert stored is not None
    assert stored.ui == {"card": "안녕"}


async def test_ok_without_ui_has_null_result_id(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_no_ui")

    assert body == {"status": "ok", "llm": {"done": True}, "resultId": None}


async def test_need_clarification_returns_candidates(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_ambiguous")

    assert body["status"] == "need_clarification"
    assert body["field"] == "cafeteria"
    assert [c["value"] for c in body["candidates"]] == ["sangrok_3f", "sangrok_2f"]


async def test_tool_error_is_returned_as_status_error(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_fail")

    assert body["status"] == "error"
    assert body["error"]["code"] == "MENU_NOT_FOUND"
    assert body["error"]["message"] == "메뉴가 없습니다."


async def test_invalid_arguments_returns_details(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_echo", {})

    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_ARGUMENTS"
    assert body["error"]["details"][0]["loc"] == ["text"]


async def test_slow_tool_times_out(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_slow")

    assert body["status"] == "error"
    assert body["error"]["code"] == "TOOL_TIMEOUT"


async def test_unexpected_exception_hides_internal_detail(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_crash/invoke", json={"arguments": {}}, headers=HEADERS
    )

    assert response.json()["error"]["code"] == "TOOL_FAILED"
    assert "secret" not in response.text


async def test_wrong_return_type_is_tool_failed(skills_client: AsyncClient) -> None:
    body = await invoke(skills_client, "test_bad_return")

    assert body["error"]["code"] == "TOOL_FAILED"


async def test_arguments_not_object_returns_400(skills_client: AsyncClient) -> None:
    response = await skills_client.post(
        "/api/v1/skills/test_echo/invoke", json={"arguments": "안녕"}, headers=HEADERS
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
