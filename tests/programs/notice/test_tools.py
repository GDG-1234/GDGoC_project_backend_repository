import pytest
from httpx import AsyncClient

import app.programs.notice.tools  # noqa: F401  (tool 등록)
from app.core.config import Settings
from tests.programs.notice.conftest import FakeDongguk

pytestmark = pytest.mark.anyio

KEY = "test-key"
HEADERS = {"X-Service-Key": KEY}


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", service_api_key=KEY)


async def test_tools_listed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/skills", headers=HEADERS)

    tools = {t["name"]: t for t in response.json()["items"]}
    assert {"notice_search", "notice_get_detail"} <= set(tools)
    schema = tools["notice_search"]["inputSchema"]
    assert "foreign_student" in schema["$defs"]["NoticeBoard"]["enum"]


async def test_invoke_search(client: AsyncClient, site: FakeDongguk) -> None:
    response = await client.post(
        "/api/v1/skills/notice_search/invoke",
        json={"arguments": {"board": "scholarship", "keyword": "국가"}},
        headers=HEADERS,
    )

    body = response.json()
    assert body["status"] == "ok"
    assert body["llm"]["items"][0]["articleId"] == 26767028


async def test_invoke_detail_bad_board(client: AsyncClient, site: FakeDongguk) -> None:
    response = await client.post(
        "/api/v1/skills/notice_get_detail/invoke",
        json={"arguments": {"board": "news", "article_id": 1}},
        headers=HEADERS,
    )

    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


async def test_invoke_detail(client: AsyncClient, site: FakeDongguk) -> None:
    response = await client.post(
        "/api/v1/skills/notice_get_detail/invoke",
        json={"arguments": {"board": "scholarship", "article_id": 26767024}},
        headers=HEADERS,
    )

    body = response.json()
    assert body["status"] == "ok"
    assert body["llm"]["articleId"] == 26767024
    assert len(body["llm"]["attachments"]) == 2
    assert body["resultId"].startswith("r_")
