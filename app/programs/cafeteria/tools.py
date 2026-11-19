from app.programs.cafeteria import service
from app.programs.cafeteria.schemas import GetMenuInput
from app.programs.registry import tool
from app.programs.schemas import ToolNeedClarification, ToolOk


@tool(
    name="cafeteria_get_menu",
    description="동국대 서울캠퍼스 상록원 학생식당(1~3층) 메뉴를 날짜별로 조회한다.",
)
async def get_menu(args: GetMenuInput) -> ToolOk | ToolNeedClarification:
    # service.today_kst를 모듈 이름으로 불러야 테스트에서 날짜를 바꿔 넣을 수 있다
    return await service.get_menu(args, today=service.today_kst())
