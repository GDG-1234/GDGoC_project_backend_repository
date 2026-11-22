"""다음 수업 판단 테스트. 실제 시간표(엑셀 샘플)를 저장해 두고 현재 시각을 바꿔 가며 본다.

샘플 시간표 (모두 신공학관 5·6층 → 길안내는 신공학관 건물까지):
- 월·수 10:30~12:00 소프트웨어공학, 13:00~15:30 시스템소프트웨어, 15:00~17:00 인공지능
- 화·목 13:00~14:30 암호학과네트워크보안, 15:00~17:00 데이터베이스설계
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.main import app
from app.timetable.service import KST, now_kst
from tests.conftest import auth

pytestmark = pytest.mark.anyio

ALICE = auth("alice@dgu.ac.kr")
NEXT = "/api/v1/timetables/me/next"
EXCEL_GRID = (Path(__file__).parent / "fixtures" / "excel_grid_paste.txt").read_text(
    encoding="utf-8"
)
FRONT_GATE_ID = 22  # 정문


def kst(day: int, hour: int, minute: int = 0) -> datetime:
    """2026-11-23(월) ~ 29(일) 중 하루."""
    return datetime(2026, 11, day, hour, minute, tzinfo=KST)


@pytest.fixture
def set_now(client: AsyncClient) -> Callable[[datetime], None]:
    # client 픽스처가 만든 뒤에 덮어써야 지워지지 않는다 (끝나면 client가 지운다).
    def setter(value: datetime) -> None:
        app.dependency_overrides[now_kst] = lambda: value

    return setter


@pytest.fixture
async def timetable(client: AsyncClient) -> None:
    preview = await client.post(
        "/api/v1/timetables/parse", json={"text": EXCEL_GRID}, headers=ALICE
    )
    await client.put(
        "/api/v1/timetables/me", json={"courses": preview.json()["courses"]}, headers=ALICE
    )


async def get_next(client: AsyncClient, **params: Any) -> dict:
    response = await client.get(NEXT, params=params, headers=ALICE)
    assert response.status_code == 200, response.text
    return response.json()


async def test_empty_timetable(client: AsyncClient, set_now: Callable) -> None:
    set_now(kst(23, 9))

    body = await get_next(client)

    assert body["next"] is None
    assert body["message"] == "등록된 시간표가 없습니다."


async def test_morning_before_first_class(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    set_now(kst(23, 9))  # 월 09:00

    body = await get_next(client)

    assert body["next"]["name"] == "소프트웨어공학"
    assert body["startsInMinutes"] == 90
    assert body["current"] is None
    # 첫 수업 전이라 출발지를 모른다 → 경로 없이 다음 수업만
    assert body["origin"] is None
    assert body["route"] is None
    assert "1시간 30분 후" in body["message"]
    assert "출발지를 고르면" in body["message"]


async def test_break_uses_previous_class_as_origin(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    set_now(kst(23, 12, 30))  # 월 12:30, 소프트웨어공학 끝나고 점심

    body = await get_next(client)

    assert body["next"]["name"] == "시스템소프트웨어"
    assert body["origin"]["source"] == "PREVIOUS_CLASS"
    assert body["origin"]["placeName"] == "신공학관"
    # 다음 수업도 신공학관이라 이동할 경로가 없다
    assert body["routeError"] == "SAME_PLACE"


async def test_during_class_uses_current_class(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    set_now(kst(23, 13, 30))  # 월 13:30, 시스템소프트웨어 중

    body = await get_next(client)

    assert body["current"]["name"] == "시스템소프트웨어"
    assert body["next"]["name"] == "인공지능"
    assert body["origin"]["source"] == "CURRENT_CLASS"
    assert body["message"].startswith("지금 수업: 시스템소프트웨어 (15:30까지)")


async def test_route_from_previous_class_in_other_building(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    extra = {
        "name": "교양",
        "day": "MON",
        "startTime": "18:00",
        "endTime": "19:00",
        "buildingName": "혜화관",
        "roomNumber": "301",
    }
    await client.post("/api/v1/timetables/me/courses", json=extra, headers=ALICE)
    set_now(kst(23, 17, 30))  # 월 17:30, 인공지능(신공학관) 끝남

    body = await get_next(client)

    assert body["next"]["name"] == "교양"
    assert body["origin"]["placeName"] == "신공학관"
    assert body["route"]["summary"]["to"]["name"] == "혜화관"
    assert body["route"]["segments"]
    assert "신공학관에서 걸어서 약" in body["message"]


async def test_requested_origin(client: AsyncClient, set_now: Callable, timetable: None) -> None:
    set_now(kst(23, 9))

    body = await get_next(client, fromPlaceId=FRONT_GATE_ID)

    assert body["origin"] == {"placeId": FRONT_GATE_ID, "placeName": "정문", "source": "REQUEST"}
    assert body["route"]["summary"]["from"]["name"] == "정문"
    assert body["route"]["summary"]["to"]["name"] == "신공학관"


async def test_unknown_origin(client: AsyncClient, set_now: Callable, timetable: None) -> None:
    set_now(kst(23, 9))

    response = await client.get(NEXT, params={"fromPlaceId": 99999}, headers=ALICE)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLACE_NOT_FOUND"


async def test_after_last_class_goes_to_next_day(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    set_now(kst(23, 18))  # 월 18:00, 오늘 수업 끝

    body = await get_next(client)

    assert body["next"]["name"] == "암호학과네트워크보안"
    assert body["next"]["day"] == "TUE"
    assert body["origin"] is None  # 내일 수업이라 오늘 강의실을 출발지로 쓰지 않는다
    assert "내일(화) 13:00" in body["message"]


async def test_weekend_goes_to_monday(
    client: AsyncClient, set_now: Callable, timetable: None
) -> None:
    set_now(kst(28, 12))  # 토 12:00

    body = await get_next(client)

    assert body["next"]["day"] == "MON"
    assert body["startsInMinutes"] == 2 * 24 * 60 - 90  # 토 12:00 → 월 10:30
    assert "월요일 10:30" in body["message"]


async def test_same_weekday_next_week(client: AsyncClient, set_now: Callable) -> None:
    only = {"name": "아침 수업", "day": "MON", "startTime": "09:00", "endTime": "10:00"}
    await client.post("/api/v1/timetables/me/courses", json=only, headers=ALICE)
    set_now(kst(23, 11))  # 월 11:00, 오늘 수업은 이미 끝남

    body = await get_next(client)

    assert body["next"]["name"] == "아침 수업"
    assert body["startsInMinutes"] == 7 * 24 * 60 - 120


async def test_course_without_building(client: AsyncClient, set_now: Callable) -> None:
    course = {"name": "온라인", "day": "MON", "startTime": "10:00", "endTime": "11:00"}
    await client.post("/api/v1/timetables/me/courses", json=course, headers=ALICE)
    set_now(kst(23, 9))

    body = await get_next(client, fromPlaceId=FRONT_GATE_ID)

    assert body["routeError"] == "NO_LOCATION"
    assert body["route"] is None
    assert "강의실 건물을 몰라" in body["message"]
