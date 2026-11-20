"""위키 docs/samples(API 명세서 v0.4 기준 실데이터 샘플)와 응답이 같은지 비교한다.

샘플의 이미지 URL은 `/static/...`이고, 우리 API는 `/api/static/...`으로 준다.
그 부분만 바꿔서 비교한다.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

SAMPLES = Path(__file__).parent / "samples"
ROUTE_FILES = sorted((SAMPLES / "routes").glob("route_[0-9][0-9].json"))


def load_sample(relative: str) -> Any:
    text = (SAMPLES / relative).read_text(encoding="utf-8")
    return json.loads(text.replace('"/static/', '"/api/static/'))


def test_all_ten_route_samples_exist() -> None:
    assert len(ROUTE_FILES) == 10


@pytest.mark.parametrize("route_file", ROUTE_FILES, ids=lambda p: p.stem)
async def test_route_sample(client: AsyncClient, route_file: Path) -> None:
    sample = load_sample(f"routes/{route_file.name}")

    response = await client.post("/api/v1/routes", json=sample["request"])

    assert response.status_code == 200
    assert response.json() == sample["response"]


async def test_route_error_sample(client: AsyncClient) -> None:
    sample = load_sample("routes/route_err_no_route.json")

    response = await client.post("/api/v1/routes", json=sample["request"])

    assert response.status_code == sample["status"] == 422
    assert response.json() == sample["response"]


async def test_map_sample(client: AsyncClient) -> None:
    response = await client.get("/api/v1/map")

    assert response.json() == load_sample("map.json")


async def test_buildings_sample(client: AsyncClient) -> None:
    response = await client.get("/api/v1/buildings")

    assert response.json() == load_sample("buildings.json")


async def test_building_detail_samples(client: AsyncClient) -> None:
    details: dict[str, Any] = load_sample("building_details.json")
    assert len(details) == 21

    for building_id, expected in details.items():
        response = await client.get(f"/api/v1/buildings/{building_id}")
        assert response.status_code == 200, building_id
        assert response.json() == expected, building_id


async def test_place_summaries_match_sample(client: AsyncClient) -> None:
    places = load_sample("places.json")["items"]
    assert len(places) == 57

    for place in places:
        response = await client.get("/api/v1/places", params={"q": place["name"], "limit": 30})
        assert place in response.json()["items"], place["name"]
