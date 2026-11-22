"""길안내 로직. 엔진을 부르고, 에러와 이미지 URL을 우리 API 형식으로 바꾼다.

API(router.py)와 AI tool(tools.py)이 함께 쓴다. tool용 함수는 아래쪽에,
다른 기능(시간표 등)이 쓰는 함수는 맨 아래에 있다.
"""

from collections.abc import Callable
from typing import Any

from app.common.exceptions import AppException
from app.common.schemas import ItemsResponse
from app.programs.navigation import repository
from app.programs.navigation.engine import ApiError, Engine
from app.programs.navigation.schemas import (
    BuildingDetailResponse,
    BuildingSummary,
    FindRouteInput,
    GetBuildingInput,
    MapInfoResponse,
    NearestPlaceResponse,
    PlaceCategory,
    PlaceSummary,
    RoomLocation,
    RouteMode,
    RouteRequest,
    RouteResponse,
    SearchPlaceInput,
)
from app.programs.schemas import Candidate, ToolError, ToolNeedClarification, ToolOk

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


# ---- AI tool용 ----
# llm에는 답변 문장에 필요한 요약만 넣는다. 좌표·이미지 같은 화면용 데이터는 ui에 넣는다.

CANDIDATE_LIMIT = 8


def _tool_call[T](fn: Callable[[], T]) -> T:
    """공용 예외를 tool 에러로 바꾼다. 예: NO_ROUTE, SAME_PLACE."""
    try:
        return fn()
    except AppException as exc:
        raise ToolError(exc.code, exc.message) from exc


def floor_label(floor: int) -> str:
    if floor == 0:
        return "실외"
    return f"B{-floor}층" if floor < 0 else f"{floor}층"


def _place_llm(place: PlaceSummary) -> dict[str, Any]:
    return {
        "name": place.name,
        "category": place.category,
        "building": place.building_name,
        "floor": floor_label(place.floor),
    }


def _place_candidate(place: PlaceSummary) -> Candidate:
    extra = [
        text
        for text in (
            place.building_name if place.building_name != place.name else None,
            floor_label(place.floor) if place.floor != 0 else None,
        )
        if text
    ]
    return Candidate(value=place.name, label=place.name, description=", ".join(extra) or None)


def resolve_place(engine: Engine, query: str, field: str) -> PlaceSummary | ToolNeedClarification:
    """장소 이름(줄임말 포함)을 장소 하나로 정한다. 애매하면 후보를 돌려준다."""
    text = query.strip()
    places = _tool_call(lambda: search_places(engine, text, None, None, CANDIDATE_LIMIT)).items
    exact = [p for p in places if p.name == text]
    if len(exact) == 1:
        return exact[0]
    if len(places) == 1:
        return places[0]
    if not places:
        raise ToolError("PLACE_NOT_FOUND", f"'{text}'에 맞는 장소가 없습니다.")
    return ToolNeedClarification(
        field=field,
        message="어느 장소인지 골라 주세요.",
        candidates=[_place_candidate(p) for p in places],
    )


def find_route_tool(engine: Engine, args: FindRouteInput) -> ToolOk | ToolNeedClarification:
    origin = resolve_place(engine, args.from_place, "from_place")
    if isinstance(origin, ToolNeedClarification):
        return origin
    destination = resolve_place(engine, args.to_place, "to_place")
    if isinstance(destination, ToolNeedClarification):
        return destination
    if origin.id == destination.id:
        raise ToolError("SAME_PLACE", "출발지와 도착지가 같습니다.")

    request = RouteRequest.model_validate(
        {
            "from": {"placeId": origin.id},
            "to": {"placeId": destination.id},
            "options": {
                "mode": args.mode,
                "avoidRoad": args.avoid_road,
                "avoidStairs": args.avoid_stairs,
                "compare": True,
            },
        }
    )
    route = _tool_call(lambda: find_route(engine, request))
    summary = route.summary
    llm = {
        "from": _place_llm(origin),
        "to": _place_llm(destination),
        "options": {
            "mode": args.mode,
            "avoidRoad": args.avoid_road,
            "avoidStairs": args.avoid_stairs,
        },
        "totalSeconds": summary.total_seconds,
        "floorChanges": summary.floor_changes,
        "usesRoad": summary.uses_road,
        "usesShortcut": summary.uses_shortcut,
        "savedSeconds": summary.saved_seconds,
        "steps": [
            {"action": step.action, "text": step.text, "seconds": step.seconds}
            for step in route.steps
        ],
        "note": (
            "지도와 경로선은 화면 카드로 함께 보여 준다. 답변에는 걸리는 시간과 주요 단계만 쓴다."
        ),
    }
    ui = {
        "request": request.model_dump(mode="json", by_alias=True),
        "route": route.model_dump(mode="json", by_alias=True),
    }
    return ToolOk(llm=llm, ui=ui)


def search_place_tool(engine: Engine, args: SearchPlaceInput) -> ToolOk:
    places = _tool_call(lambda: search_places(engine, args.query, None, None, args.limit)).items
    return ToolOk(
        llm={
            "query": args.query,
            "places": [_place_llm(p) for p in places],
            "note": None if places else "맞는 장소가 없습니다. 다른 이름이나 줄임말로 다시 찾는다.",
        }
    )


def _normalize(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace() and ch not in "·_").lower()


def resolve_building(engine: Engine, query: str) -> BuildingSummary | ToolNeedClarification:
    """건물 이름이나 별칭으로 건물 하나를 정한다. 애매하면 후보를 돌려준다."""
    q = _normalize(query)
    buildings = list_buildings(engine).items
    exact = [b for b in buildings if q in {_normalize(n) for n in (b.name, *b.aliases)}]
    if len(exact) == 1:
        return exact[0]
    partial = exact or [
        b for b in buildings if any(q in _normalize(n) for n in (b.name, *b.aliases))
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise ToolError("BUILDING_NOT_FOUND", f"'{query.strip()}'에 맞는 건물이 없습니다.")
    return ToolNeedClarification(
        field="building",
        message="어느 건물인지 골라 주세요.",
        candidates=[Candidate(value=b.name, label=b.name) for b in partial[:CANDIDATE_LIMIT]],
    )


def get_building_tool(engine: Engine, args: GetBuildingInput) -> ToolOk | ToolNeedClarification:
    building = resolve_building(engine, args.building)
    if isinstance(building, ToolNeedClarification):
        return building
    detail = _tool_call(lambda: get_building(engine, building.id))
    llm = {
        "name": detail.name,
        "aliases": detail.aliases,
        "phone": detail.phone,
        "operatingHours": detail.operating_hours,
        "floorsWithGuide": [f.label for f in detail.floors],
        "facilities": [
            {"type": f.type, "name": f.name, "floor": f.floor_description}
            for f in detail.facilities
        ],
        "note": "floorsWithGuide는 길안내 데이터가 있는 층이다. 건물의 실제 층수와 다를 수 있다.",
    }
    return ToolOk(llm=llm, ui=detail.model_dump(mode="json", by_alias=True))


# ---- 다른 기능이 쓰는 함수 ----


def _exact_place(engine: Engine, name: str, building_id: int) -> PlaceSummary | None:
    places = search_places(engine, name, None, building_id, 30).items
    return next((p for p in places if p.name == name), None)


def locate_room(building_name: str | None, floor: int | None) -> RoomLocation | None:
    """건물 이름과 층을 길안내 장소로 바꾼다. 건물을 못 찾으면 None.

    그 층의 장소가 있으면 층까지(FLOOR), 없으면 건물까지(BUILDING) 안내한다.
    강의실 단위 데이터는 아직 없다.
    """
    if not building_name:
        return None
    engine = repository.get_engine()
    try:
        building = resolve_building(engine, building_name)
    except ToolError:
        return None
    if isinstance(building, ToolNeedClarification):
        return None

    if floor:
        floor_place = _exact_place(engine, f"{building.name} {floor_label(floor)}", building.id)
        if floor_place is not None:
            return RoomLocation(
                building_id=building.id,
                building_name=building.name,
                floor=floor,
                place_id=floor_place.id,
                place_name=floor_place.name,
                precision="FLOOR",
            )
    building_place = _exact_place(engine, building.name, building.id)
    return RoomLocation(
        building_id=building.id,
        building_name=building.name,
        floor=floor,
        place_id=building_place.id if building_place else None,
        place_name=building_place.name if building_place else None,
        precision="BUILDING",
    )


def get_place(place_id: int) -> PlaceSummary | None:
    place = repository.get_engine().places.get(place_id)
    return PlaceSummary.model_validate(place) if place is not None else None


def route_between(
    from_place_id: int,
    to_place_id: int,
    *,
    mode: RouteMode = "FASTEST",
    avoid_road: bool = False,
    avoid_stairs: bool = False,
) -> RouteResponse:
    """장소 id 두 개 사이의 경로. 실패하면 AppException(NO_ROUTE, SAME_PLACE 등)."""
    request = RouteRequest.model_validate(
        {
            "from": {"placeId": from_place_id},
            "to": {"placeId": to_place_id},
            "options": {"mode": mode, "avoidRoad": avoid_road, "avoidStairs": avoid_stairs},
        }
    )
    return find_route(repository.get_engine(), request)
