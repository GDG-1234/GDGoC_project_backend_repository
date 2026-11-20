"""길안내 API 로직. 엔진을 부르고, 에러와 이미지 URL을 우리 API 형식으로 바꾼다."""

from collections.abc import Callable
from typing import Any

from app.common.exceptions import AppException
from app.common.schemas import ItemsResponse
from app.programs.navigation.engine import ApiError, Engine
from app.programs.navigation.schemas import (
    BuildingDetailResponse,
    BuildingSummary,
    MapInfoResponse,
    NearestPlaceResponse,
    PlaceCategory,
    PlaceSummary,
    RouteRequest,
    RouteResponse,
)

# 엔진 데이터의 이미지 URL은 `/static/...`이다. 배포 시 Firebase Hosting이 `/api/**`만
# 백엔드로 넘기므로 `/api/static/...`으로 바꿔서 준다 (app/main.py의 mount와 짝).
ENGINE_STATIC_PREFIX = "/static/"
PUBLIC_STATIC_PREFIX = "/api/static/"


def to_public_url(url: str | None) -> str | None:
    if url is not None and url.startswith(ENGINE_STATIC_PREFIX):
        return PUBLIC_STATIC_PREFIX + url.removeprefix(ENGINE_STATIC_PREFIX)
    return url


def _call[T](fn: Callable[[], T]) -> T:
    """엔진의 ApiError를 공용 예외로 바꾼다. 응답 형식은 같다 ({"error": {code, message}})."""
    try:
        return fn()
    except ApiError as exc:
        raise AppException(exc.status, exc.code, exc.message) from exc


def _with_public_urls(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {**data, **{key: to_public_url(data.get(key)) for key in keys if key in data}}


def get_map(engine: Engine) -> MapInfoResponse:
    data = _call(engine.get_map)
    return MapInfoResponse.model_validate(_with_public_urls(data, "imageUrl"))


def search_places(
    engine: Engine,
    q: str,
    category: PlaceCategory | None,
    building_id: int | None,
    limit: int,
) -> ItemsResponse[PlaceSummary]:
    data = _call(lambda: engine.search_places(q, category, building_id, limit))
    return ItemsResponse[PlaceSummary].model_validate(data)


def nearest_place(engine: Engine, x: float, y: float, floor: int) -> NearestPlaceResponse:
    data = _call(lambda: engine.nearest_place(x, y, floor))
    return NearestPlaceResponse.model_validate(data)


def find_route(engine: Engine, request: RouteRequest) -> RouteResponse:
    body = request.model_dump(by_alias=True)
    data = _call(lambda: engine.route(body))
    data["segments"] = [_with_public_urls(s, "floorImageUrl") for s in data["segments"]]
    return RouteResponse.model_validate(data)


def list_buildings(engine: Engine) -> ItemsResponse[BuildingSummary]:
    data = _call(engine.list_buildings)
    items = [_with_public_urls(b, "thumbnailUrl") for b in data["items"]]
    return ItemsResponse[BuildingSummary].model_validate({"items": items})


def get_building(engine: Engine, building_id: int) -> BuildingDetailResponse:
    data = _call(lambda: engine.building_detail(building_id))
    data = _with_public_urls(data, "photoUrl")
    data["floors"] = [_with_public_urls(f, "floorImageUrl") for f in data["floors"]]
    return BuildingDetailResponse.model_validate(data)
