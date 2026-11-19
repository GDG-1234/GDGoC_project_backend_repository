import datetime as dt

from pydantic import BaseModel, Field

from app.common.schemas import CamelModel

# ---- tool 입력 (LLM이 보는 JSON Schema라 BaseModel을 쓴다) ----


class GetMenuInput(BaseModel):
    date: dt.date | None = Field(None, description="조회할 날짜 YYYY-MM-DD. 없으면 오늘(한국 시간)")
    cafeteria: str | None = Field(
        None, description="식당 이름 일부. 예: 3층, 2층, 솥앤누들, 교직원식당. 없으면 전체"
    )


# ---- 생협 페이지에서 읽은 데이터 ----


class MealMenu(CamelModel):
    meal: str  # 끼니: 중식, 석식, 중·석식
    corner: str | None  # 코너: 집밥, 일품코너 ... 머리 행보다 칸이 많으면 None
    menu: str  # 칸 텍스트 그대로 (메뉴·가격·원산지가 섞여 있다)


class Cafeteria(CamelModel):
    name: str
    closed: bool
    meals: list[MealMenu]


class DayMenu(CamelModel):
    date: dt.date
    cafeterias: list[Cafeteria]
