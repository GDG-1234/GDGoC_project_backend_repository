"""길안내 API 요청·응답 모델. 위키 API 명세서 v0.4의 2장 타입과 같다 (JSON은 camelCase)."""

from typing import Literal

from pydantic import Field

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
