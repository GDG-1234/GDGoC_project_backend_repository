"""길안내 API 6개 (위키 API 명세서 v0.4 1~7장).

엔드포인트를 모두 `async def`로 두는 이유: 엔진의 경로 계산은 공유 간선 데이터에 임시 값을
써넣었다가 지운다. `def`로 두면 FastAPI가 스레드 풀에서 동시에 돌려 값이 섞일 수 있다.
`async def` 안에서 엔진을 바로 부르면 중간에 `await`가 없어서 한 요청씩 끝까지 실행된다.
경로 계산은 몇 ms라 이벤트 루프를 오래 막지 않는다. (리마스터 때 공유 데이터 수정을 없앤다)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.schemas import ItemsResponse
from app.programs.navigation import service
from app.programs.navigation.engine import Engine
from app.programs.navigation.repository import get_engine
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

router = APIRouter(prefix="/api/v1")

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get(
    "/map",
    response_model=MapInfoResponse,
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="지도 이미지 정보",
)
async def read_map(engine: EngineDep) -> MapInfoResponse:
    return service.get_map(engine)


@router.get(
    "/places",
    response_model=ItemsResponse[PlaceSummary],
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="장소 검색 (자동완성)",
)
async def search_places(
    engine: EngineDep,
    q: Annotated[str, Query(min_length=1, description="검색어. 별칭도 검색된다")],
    category: PlaceCategory | None = None,
    building_id: Annotated[int | None, Query(alias="buildingId")] = None,
    limit: Annotated[int, Query(description="기본 10, 1~30으로 맞춘다")] = 10,
) -> ItemsResponse[PlaceSummary]:
    return service.search_places(engine, q, category, building_id, limit)


@router.get(
    "/places/nearest",
    response_model=NearestPlaceResponse,
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="지도에서 클릭한 곳과 가장 가까운 장소",
)
async def read_nearest_place(
    engine: EngineDep,
    x: float,
    y: float,
    floor: int = 0,
) -> NearestPlaceResponse:
    return service.nearest_place(engine, x, y, floor)


@router.post(
    "/routes",
    response_model=RouteResponse,
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="경로 계산",
)
async def create_route(engine: EngineDep, body: RouteRequest) -> RouteResponse:
    return service.find_route(engine, body)


@router.get(
    "/buildings",
    response_model=ItemsResponse[BuildingSummary],
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="건물 목록",
)
async def list_buildings(engine: EngineDep) -> ItemsResponse[BuildingSummary]:
    return service.list_buildings(engine)


@router.get(
    "/buildings/{building_id}",
    response_model=BuildingDetailResponse,
    status_code=status.HTTP_200_OK,
    tags=["navigation"],
    summary="건물 상세 (층, 편의시설)",
)
async def read_building(engine: EngineDep, building_id: int) -> BuildingDetailResponse:
    return service.get_building(engine, building_id)
