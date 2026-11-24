from app.programs.navigation import service
from app.programs.navigation.repository import get_engine
from app.programs.navigation.schemas import FindRouteInput, GetBuildingInput, SearchPlaceInput
from app.programs.registry import tool
from app.programs.schemas import ToolNeedClarification, ToolOk


@tool(
    name="navigation_find_route",
    description=(
        "동국대 서울캠퍼스 안에서 출발 장소부터 도착 장소까지 걸어가는 길을 찾는다. "
        "건물 안 층 이동(계단·엘리베이터)을 포함한다. 장소는 이름이나 줄임말로 넣는다. "
        "현재 위치는 알 수 없으니 출발지를 모르면 먼저 사용자에게 물어본다. "
        "지도와 경로선은 화면 카드로 나가므로 답변에는 걸리는 시간과 주요 단계만 쓴다."
    ),
)
async def find_route(args: FindRouteInput) -> ToolOk | ToolNeedClarification:
    return service.find_route_tool(get_engine(), args)


@tool(
    name="navigation_search_place",
    description=(
        "동국대 서울캠퍼스에서 길안내할 수 있는 장소(건물, 건물의 층, 입구, 광장)를 "
        "이름으로 찾는다. 어떤 장소가 있는지 확인하거나 이름이 애매할 때 쓴다."
    ),
)
async def search_place(args: SearchPlaceInput) -> ToolOk:
    return service.search_place_tool(get_engine(), args)


@tool(
    name="navigation_get_building",
    description=(
        "동국대 서울캠퍼스 건물 정보(전화번호, 운영 시간, 편의시설, 길안내가 되는 층)를 가져온다."
    ),
)
async def get_building(args: GetBuildingInput) -> ToolOk | ToolNeedClarification:
    return service.get_building_tool(get_engine(), args)
