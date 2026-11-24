import json
from pathlib import Path

import pytest
from httpx import AsyncClient

import app.programs.navigation.tools  # noqa: F401  (tool 등록)
from app.core.config import Settings
from app.programs.navigation import service
from app.programs.navigation.repository import get_engine
from app.programs.navigation.schemas import FindRouteInput, GetBuildingInput
from app.programs.schemas import ToolOk

pytestmark = pytest.mark.anyio

KEY = "test-key"
HEADERS = {"X-Service-Key": KEY}
SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite://", service_api_key=KEY)


async def invoke(client: AsyncClient, name: str, **arguments: object) -> dict:
    response = await client.post(
        f"/api/v1/skills/{name}/invoke", json={"arguments": arguments}, headers=HEADERS
    )
    assert response.status_code == 200
    return response.json()


def sample_route(name: str) -> dict:
    return json.loads((SAMPLES / "routes" / name).read_text(encoding="utf-8"))["response"]


# ---- 목록 ----


async def test_tools_listed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/skills", headers=HEADERS)

    tools = {t["name"]: t for t in response.json()["items"]}
    assert {
        "navigation_find_route",
        "navigation_search_place",
        "navigation_get_building",
    } <= set(tools)
    route_props = tools["navigation_find_route"]["inputSchema"]["properties"]
    assert {"from_place", "to_place", "mode", "avoid_road", "avoid_stairs"} <= set(route_props)


# ---- 경로 ----


async def test_find_route_same_as_api(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="정문", to_place="중앙도서관")

    assert body["status"] == "ok"
    assert body["resultId"].startswith("r_")
    llm = body["llm"]
    assert llm["from"]["name"] == "정문"
    assert llm["to"]["name"] == "중앙도서관"
    assert llm["totalSeconds"] == sample_route("route_01.json")["summary"]["totalSeconds"]
    assert llm["steps"][0]["action"] == "START"
    assert llm["steps"][-1]["action"] == "ARRIVE"


async def test_find_route_llm_has_no_map_data(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="정문", to_place="중앙도서관")

    text = json.dumps(body["llm"], ensure_ascii=False)
    for key in ("segments", "points", "position", "floorImageUrl"):
        assert key not in text


async def test_find_route_alias_and_floor_place(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="중도", to_place="신공학관 4층")

    assert body["status"] == "ok"
    assert body["llm"]["from"]["name"] == "중앙도서관"
    assert body["llm"]["to"]["name"] == "신공학관 4층"
    assert body["llm"]["to"]["floor"] == "4층"


async def test_find_route_options(client: AsyncClient) -> None:
    body = await invoke(
        client,
        "navigation_find_route",
        from_place="학술관 4층",
        to_place="경영관 2층",
        mode="EASIEST",
    )

    assert body["status"] == "ok"
    assert body["llm"]["options"]["mode"] == "EASIEST"


async def test_find_route_ambiguous_place(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="신공", to_place="정문")

    assert body["status"] == "need_clarification"
    assert body["field"] == "from_place"
    values = [c["value"] for c in body["candidates"]]
    assert "신공학관" in values
    assert "신공학관 4층" in values


async def test_find_route_candidate_value_resolves(client: AsyncClient) -> None:
    first = await invoke(client, "navigation_find_route", from_place="신공", to_place="정문")
    picked = first["candidates"][0]["value"]

    body = await invoke(client, "navigation_find_route", from_place=picked, to_place="정문")

    assert body["status"] == "ok"
    assert body["llm"]["from"]["name"] == picked


async def test_find_route_unknown_place(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="없는장소xyz", to_place="정문")

    assert body["status"] == "error"
    assert body["error"]["code"] == "PLACE_NOT_FOUND"


async def test_find_route_same_place(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="정문", to_place="정문")

    assert body["error"]["code"] == "SAME_PLACE"


async def test_find_route_no_route_without_stairs(client: AsyncClient) -> None:
    # 샘플 route_err_no_route: 과학관 → 후문은 계단 없이 갈 수 없다
    body = await invoke(
        client, "navigation_find_route", from_place="과학관", to_place="후문", avoid_stairs=True
    )

    assert body["error"]["code"] == "NO_ROUTE"


async def test_find_route_missing_destination(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_find_route", from_place="정문")

    assert body["error"]["code"] == "INVALID_ARGUMENTS"


def test_find_route_ui_is_route_response() -> None:
    result = service.find_route_tool(
        get_engine(), FindRouteInput(from_place="정문", to_place="중앙도서관")
    )

    assert isinstance(result, ToolOk)
    assert result.ui is not None
    assert result.ui["request"]["from"]["placeId"] == 22
    route = result.ui["route"]
    assert route["summary"]["totalSeconds"] == result.llm["totalSeconds"]
    assert route["segments"][0]["points"]


def test_find_route_ui_uses_public_image_urls() -> None:
    # 샘플 route_04: 혜화관 → 신공학관 3층은 단면도가 있는 실내 구간을 지난다
    result = service.find_route_tool(
        get_engine(), FindRouteInput(from_place="혜화관", to_place="신공학관 3층")
    )

    assert isinstance(result, ToolOk)
    assert result.ui is not None
    urls = [s["floorImageUrl"] for s in result.ui["route"]["segments"] if s["floorImageUrl"]]
    assert urls
    assert all(url.startswith("/api/static/") for url in urls)


# ---- 장소 검색 ----


async def test_search_place(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_search_place", query="학식")

    assert body["status"] == "ok"
    assert body["resultId"] is None
    assert [p["name"] for p in body["llm"]["places"]] == ["상록원"]


async def test_search_place_none(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_search_place", query="없는장소xyz")

    assert body["llm"]["places"] == []
    assert body["llm"]["note"]


# ---- 건물 ----


@pytest.mark.parametrize(
    ("query", "name"),
    [("중도", "중앙도서관"), ("경영관", "사회과학관·경영관"), ("신공", "신공학관")],
)
async def test_get_building_by_alias(client: AsyncClient, query: str, name: str) -> None:
    body = await invoke(client, "navigation_get_building", building=query)

    assert body["status"] == "ok"
    assert body["llm"]["name"] == name
    assert body["resultId"].startswith("r_")


async def test_get_building_unknown(client: AsyncClient) -> None:
    body = await invoke(client, "navigation_get_building", building="없는건물xyz")

    assert body["error"]["code"] == "BUILDING_NOT_FOUND"


def test_get_building_ui_is_building_detail() -> None:
    result = service.get_building_tool(get_engine(), GetBuildingInput(building="신공학관"))

    assert isinstance(result, ToolOk)
    assert result.ui is not None
    assert result.ui["name"] == "신공학관"
    assert result.llm["floorsWithGuide"] == [f["label"] for f in result.ui["floors"]]
    assert all(
        f["floorImageUrl"].startswith("/api/static/")
        for f in result.ui["floors"]
        if f["floorImageUrl"]
    )
