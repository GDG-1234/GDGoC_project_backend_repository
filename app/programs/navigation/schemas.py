"""길안내 API 요청·응답 모델. 위키 API 명세서 v0.4의 2장 타입과 같다 (JSON은 camelCase).

맨 아래에 AI tool 입력 모델이 있다.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.common.schemas import CamelModel

PlaceCategory = Literal[
    "BUILDING", "ENTRANCE", "CLASSROOM", "LIBRARY", "CAFETERIA", "FACILITY", "LANDMARK"
]
RouteMode = Literal["FASTEST", "EASIEST"]
FacilityType = Literal["VENDING", "PRINTER", "ATM", "STORE", "CAFE", "LOUNGE", "SHOWER", "ETC"]
StepAction = Literal[
    "START",
    "WALK",
    "ENTER_BUILDING",
    "EXIT_BUILDING",
    "STAIRS_UP",
    "STAIRS_DOWN",
    "ELEVATOR",
    "UPHILL",
    "DOWNHILL",
    "ARRIVE",
]


class Point(CamelModel):
    x: float
    y: float


class ImageBounds(CamelModel):
    """층 단면도를 지도 위에 겹칠 위치와 크기 (지도 픽셀, 왼쪽 위 기준)."""

    x: float
    y: float
    width: float
    height: float


# ---- 지도, 장소 ----


class MapInfoResponse(CamelModel):
    image_url: str
    width: int
    height: int
    default_center: Point
    min_zoom: int
    max_zoom: int


class PlaceSummary(CamelModel):
    id: int
    name: str
    category: PlaceCategory
    building_id: int | None
    building_name: str | None
    floor: int
    position: Point


class NearestPlaceResponse(CamelModel):
    place: PlaceSummary
    distance_px: float


# ---- 경로 ----


class RoutePlaceInput(CamelModel):
    place_id: int


class RouteOptions(CamelModel):
    mode: RouteMode = "FASTEST"
    avoid_road: bool = False
    avoid_stairs: bool = False
    compare: bool = False


class RouteRequest(CamelModel):
    from_: RoutePlaceInput = Field(alias="from")
    to: RoutePlaceInput
    options: RouteOptions = Field(default_factory=RouteOptions)


class PlaceRef(CamelModel):
    id: int
    name: str


class RouteSummary(CamelModel):
    from_: PlaceRef = Field(alias="from")
    to: PlaceRef
    total_seconds: int
    total_kcal: float
    floor_changes: int
    uses_road: bool
    uses_shortcut: bool
    saved_seconds: int | None


class RoutePoint(CamelModel):
    node_id: int
    x: float
    y: float


class RouteSegment(CamelModel):
    index: int
    indoor: bool
    building_id: int | None
    floor: int
    floor_image_url: str | None
    floor_image_bounds: ImageBounds | None
    is_shortcut: bool
    name: str | None
    points: list[RoutePoint]


class RouteStep(CamelModel):
    index: int
    action: StepAction
    text: str
    position: Point
    segment_index: int
    floor: int
    seconds: int | None


class RouteResponse(CamelModel):
    summary: RouteSummary
    segments: list[RouteSegment]
    steps: list[RouteStep]


# ---- 건물 ----


class BuildingSummary(CamelModel):
    id: int
    name: str
    aliases: list[str]
    position: Point
    thumbnail_url: str | None


class BuildingFloor(CamelModel):
    floor: int
    label: str
    floor_image_url: str | None
    floor_image_bounds: ImageBounds | None


class Facility(CamelModel):
    type: FacilityType
    name: str
    floor_description: str | None


class BuildingDetailResponse(CamelModel):
    id: int
    name: str
    aliases: list[str]
    position: Point
    photo_url: str | None
    phone: str | None
    operating_hours: str | None
    floors: list[BuildingFloor]
    facilities: list[Facility]


# ---- AI tool 입력 (LLM이 보는 JSON Schema라 BaseModel을 쓴다) ----

PLACE_EXAMPLES = "예: 정문, 중도, 신공학관 4층, 혜화관 1층, 학식"


class FindRouteInput(BaseModel):
    from_place: str = Field(
        min_length=1,
        max_length=50,
        description=f"출발 장소 이름이나 줄임말. {PLACE_EXAMPLES}. "
        "현재 위치는 알 수 없으므로 사용자가 말하지 않았으면 먼저 물어본다",
    )
    to_place: str = Field(
        min_length=1, max_length=50, description=f"도착 장소 이름이나 줄임말. {PLACE_EXAMPLES}"
    )
    mode: RouteMode = Field(
        "FASTEST", description="FASTEST=가장 빠른 길, EASIEST=덜 힘든 길(오르막·계단이 적은 길)"
    )
    avoid_road: bool = Field(False, description="차도를 되도록 피한다")
    avoid_stairs: bool = Field(
        False, description="계단을 쓰지 않는다(엘리베이터 이용). 켜면 길이 없을 수 있다"
    )


class SearchPlaceInput(BaseModel):
    query: str = Field(
        min_length=1, max_length=50, description=f"찾을 장소 이름이나 줄임말. {PLACE_EXAMPLES}"
    )
    limit: int = Field(5, ge=1, le=10, description="가져올 개수")


class GetBuildingInput(BaseModel):
    building: str = Field(
        min_length=1,
        max_length=50,
        description="건물 이름이나 줄임말. 예: 신공학관, 신공, 중도, 상록원, 경영관",
    )
