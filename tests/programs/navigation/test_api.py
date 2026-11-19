import asyncio
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.programs.navigation.repository import STATIC_DIR, get_engine
from app.programs.navigation.service import to_public_url

pytestmark = pytest.mark.anyio

SAMPLES = Path(__file__).parent / "samples"

# 샘플 route_01: 정문(22) → 중앙도서관(16)
FRONT_GATE_ID = 22
LIBRARY_ID = 16


def route_body(from_id: int, to_id: int, **options: object) -> dict:
    return {"from": {"placeId": from_id}, "to": {"placeId": to_id}, "options": options}


# ---- 데이터 위치 ----


def test_engine_loads_from_package_data() -> None:
    assert get_engine().get_map()["width"] == 3000
    assert (STATIC_DIR / "map" / "campus.png").is_file()


def test_to_public_url() -> None:
    assert to_public_url("/static/floor/a.png") == "/api/static/floor/a.png"
    assert to_public_url(None) is None
    assert to_public_url("https://example.com/a.png") == "https://example.com/a.png"


# ---- 지도 ----


async def test_map_returns_api_static_url(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/map")).json()

    assert body["imageUrl"] == "/api/static/map/campus.png"
    assert body["width"] == 3000
    assert body["defaultCenter"] == {"x": 1100, "y": 2600}


# ---- 장소 검색 ----


async def test_search_by_alias(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/places", params={"q": "신공"})).json()

    assert body["items"]
    assert "신공학관" in body["items"][0]["name"]


async def test_search_exact_match_first(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/places", params={"q": "중앙도서관"})).json()

    assert body["items"][0]["name"] == "중앙도서관"


async def test_search_no_match_is_empty_list(client: AsyncClient) -> None:
    response = await client.get("/api/v1/places", params={"q": "없는장소이름"})

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_search_limit_clamped(client: AsyncClient) -> None:
    response = await client.get("/api/v1/places", params={"q": "관", "limit": 31})

    assert response.status_code == 200
    assert 0 < len(response.json()["items"]) <= 30


@pytest.mark.parametrize("q", ["", " "], ids=["empty", "blank"])
async def test_search_blank_q_is_400(client: AsyncClient, q: str) -> None:
    response = await client.get("/api/v1/places", params={"q": q})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_search_unknown_category_is_400(client: AsyncClient) -> None:
    response = await client.get("/api/v1/places", params={"q": "관", "category": "PIZZA"})

    assert response.status_code == 400


async def test_search_category_filter(client: AsyncClient) -> None:
    params = {"q": "문", "category": "ENTRANCE", "limit": 30}
    items = (await client.get("/api/v1/places", params=params)).json()["items"]

    assert items
    assert {item["category"] for item in items} == {"ENTRANCE"}


# ---- 지도에서 선택 ----


async def test_nearest_returns_place(client: AsyncClient) -> None:
    gate = get_engine().places[FRONT_GATE_ID]["position"]

    response = await client.get("/api/v1/places/nearest", params=gate)

    body = response.json()
    assert body["place"]["id"] == FRONT_GATE_ID
    assert body["distancePx"] == 0.0


async def test_nearest_floor_without_places_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/places/nearest", params={"x": 1, "y": 1, "floor": 99})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLACE_NOT_FOUND"


# ---- 경로 ----


async def test_route_without_options_ok(client: AsyncClient) -> None:
    body = {"from": {"placeId": FRONT_GATE_ID}, "to": {"placeId": LIBRARY_ID}}

    response = await client.post("/api/v1/routes", json=body)

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["from"] == {"id": FRONT_GATE_ID, "name": "정문"}
    assert summary["to"]["id"] == LIBRARY_ID


async def test_route_same_place_is_400(client: AsyncClient) -> None:
    response = await client.post("/api/v1/routes", json=route_body(LIBRARY_ID, LIBRARY_ID))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SAME_PLACE"


async def test_route_unknown_place_is_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/routes", json=route_body(FRONT_GATE_ID, 99999))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLACE_NOT_FOUND"


async def test_route_bad_mode_is_400(client: AsyncClient) -> None:
    body = route_body(FRONT_GATE_ID, LIBRARY_ID, mode="FLYING")

    response = await client.post("/api/v1/routes", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_route_missing_place_id_is_400(client: AsyncClient) -> None:
    response = await client.post("/api/v1/routes", json={"from": {}, "to": {"placeId": 1}})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_route_images_use_api_static(client: AsyncClient) -> None:
    # 샘플 route_04: 혜화관 → 신공학관 3층 (층 단면도가 있는 실내 구간 포함)
    sample = json.loads((SAMPLES / "routes" / "route_04.json").read_text(encoding="utf-8"))

    response = await client.post("/api/v1/routes", json=sample["request"])

    urls = [s["floorImageUrl"] for s in response.json()["segments"] if s["floorImageUrl"]]
    assert urls
    assert all(url.startswith("/api/static/floor/") for url in urls)


async def test_concurrent_routes_match_sequential(client: AsyncClient) -> None:
    bodies = [route_body(a, b) for a, b in [(22, 16), (16, 22), (1, 23), (23, 1)]] * 3
    sequential = [(await client.post("/api/v1/routes", json=b)).json() for b in bodies]

    responses = await asyncio.gather(*(client.post("/api/v1/routes", json=b) for b in bodies))

    assert [r.json() for r in responses] == sequential


# ---- 건물 ----


async def test_buildings_have_api_static_thumbnails(client: AsyncClient) -> None:
    items = (await client.get("/api/v1/buildings")).json()["items"]

    assert len(items) == 21
    assert all(item["thumbnailUrl"].startswith("/api/static/") for item in items)


async def test_building_not_found_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/buildings/99999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BUILDING_NOT_FOUND"


# ---- 이미지 ----


async def test_static_image_served(client: AsyncClient) -> None:
    response = await client.get("/api/static/map/campus.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


async def test_missing_static_image_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/static/map/nothing.png")

    assert response.status_code == 404
