from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.common.schemas import CamelModel
from app.programs.navigation.schemas import RoomLocation, RouteResponse

Day = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

MAX_PASTE_LENGTH = 50_000
MAX_COURSES = 100


# 사용자에게 보여 줄 엑셀 받는 방법 (프론트 안내 문구로 쓴다)
EXCEL_GUIDE = (
    "nDRIMS 로그인 → 수업/강의평가 → 개인강의 시간표조회 → 톱니바퀴(설정)에서 엑셀로 다운로드 → "
    "엑셀에서 시간표 부분을 드래그해서 복사 → 붙여넣기"
)


class ParseTimetableRequest(CamelModel):
    text: str = Field(
        min_length=1,
        max_length=MAX_PASTE_LENGTH,
        description=f"엑셀 시간표를 드래그·복사해서 붙여넣은 글자 그대로. 받는 방법: {EXCEL_GUIDE}",
    )


class CourseInput(CamelModel):
    """수업 하나. 직접 입력할 때는 name, day, startTime, endTime만 있으면 된다."""

    name: str = Field(min_length=1, max_length=100, description="과목명")
    day: Day
    start_time: str = Field(pattern=TIME_PATTERN, description="HH:MM")
    end_time: str = Field(pattern=TIME_PATTERN, description="HH:MM")
    building_name: str | None = Field(
        None,
        max_length=100,
        description="건물 이름. 길안내 건물 목록(GET /buildings)의 name을 쓰면 길안내와 연결된다",
    )
    room_number: str | None = Field(
        None, max_length=20, description="호실. 예: 5145 (앞자리로 층을 추정한다)"
    )
    room_description: str | None = Field(None, max_length=100, description="강의실 설명이나 메모")
    weeks: str | None = Field(None, max_length=50, description="예: 1주차~15주차")
    room: str | None = Field(
        None,
        max_length=200,
        description="엑셀 강의실 칸 원문. buildingName·roomNumber가 비어 있으면 여기서 읽는다",
    )

    @model_validator(mode="after")
    def check_time_order(self) -> Self:
        if self.start_time >= self.end_time:
            raise ValueError("끝나는 시간은 시작 시간보다 늦어야 합니다.")
        return self


class Course(CourseInput):
    id: int | None = Field(description="저장된 수업 id. 미리보기(parse)에서는 null")
    floor: int | None = Field(description="호실 번호로 추정한 층. 모르면 null")
    location: RoomLocation | None = Field(description="길안내 장소. 건물을 못 찾으면 null")


class ParseTimetableResponse(CamelModel):
    courses: list[Course]
    warnings: list[str]


class SaveTimetableRequest(CamelModel):
    courses: list[CourseInput] = Field(max_length=MAX_COURSES)


class TimetableResponse(CamelModel):
    courses: list[Course]
    updated_at: datetime | None


# ---- 다음 수업 ----

OriginSource = Literal["REQUEST", "CURRENT_CLASS", "PREVIOUS_CLASS"]


class NextOrigin(CamelModel):
    place_id: int
    place_name: str
    source: OriginSource = Field(
        description=(
            "REQUEST=요청한 출발지, CURRENT_CLASS=지금 듣는 수업, PREVIOUS_CLASS=오늘 직전 수업"
        )
    )


class NextCourseResponse(CamelModel):
    now: datetime = Field(description="판단 기준 시각 (한국 시간)")
    current: Course | None = Field(description="지금 듣고 있는 수업")
    next: Course | None = Field(description="다음 수업. 시간표가 비어 있으면 null")
    starts_in_minutes: int | None = Field(description="다음 수업까지 남은 분")
    origin: NextOrigin | None = Field(
        description="경로 출발지. 정할 수 없으면 null (화면에서 출발지를 물어본다)"
    )
    route: RouteResponse | None = Field(description="출발지 → 다음 수업 장소 경로")
    route_error: str | None = Field(
        description=(
            "경로를 못 만든 이유. NO_LOCATION(강의실 건물을 모름), SAME_PLACE(같은 곳), "
            "FLOOR_ROUTE_UNAVAILABLE(같은 건물 다른 층인데 층 사이 데이터 없음), NO_ROUTE 등"
        )
    )
    message: str = Field(description="화면에 그대로 보여 줄 수 있는 한 줄 요약")
