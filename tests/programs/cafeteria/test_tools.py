import datetime as dt

import pytest
from httpx import AsyncClient

import app.programs.cafeteria.tools  # noqa: F401  (tool 등록)
from app.core.config import Settings
from app.programs.cafeteria import service
from tests.programs.cafeteria.conftest import FakeCoop

pytestmark = pytest.mark.anyio

KEY = "test-key"
HEADERS = {"X-Service-Key": KEY}
INVOKE = "/api/v1/skills/cafeteria_get_menu/invoke"


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", service_api_key=KEY)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "today_kst", lambda: dt.date(2026, 11, 19))


async def test_tool_listed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/skills", headers=HEADERS)

    tools = {t["name"]: t for t in response.json()["items"]}
    assert "cafeteria_get_menu" in tools
    assert {"date", "cafeteria"} <= set(tools["cafeteria_get_menu"]["inputSchema"]["properties"])


async def test_invoke_ok(client: AsyncClient, coop: FakeCoop) -> None:
    response = await client.post(INVOKE, json={"arguments": {}}, headers=HEADERS)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["llm"]["date"] == "2026-11-19"
    assert body["resultId"].startswith("r_")


async def test_invoke_bad_date(client: AsyncClient, coop: FakeCoop) -> None:
    response = await client.post(INVOKE, json={"arguments": {"date": "어제"}}, headers=HEADERS)

    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


async def test_invoke_source_down(client: AsyncClient, coop: FakeCoop) -> None:
    coop.down = True

    response = await client.post(INVOKE, json={"arguments": {}}, headers=HEADERS)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "error"
    assert body["error"]["code"] == "SOURCE_UNAVAILABLE"
