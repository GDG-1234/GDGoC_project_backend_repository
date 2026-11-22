from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.programs.navigation.service import locate_room
from app.timetable.schemas import MAX_COURSES
from tests.conftest import auth

pytestmark = pytest.mark.anyio

ALICE = auth("alice@dgu.ac.kr")
BOB = auth("bob@dgu.ac.kr")
COURSES = "/api/v1/timetables/me/courses"
MINE = "/api/v1/timetables/me"
EXCEL_GRID = (Path(__file__).parent / "fixtures" / "excel_grid_paste.txt").read_text(
    encoding="utf-8"
)

MANUAL = {
    "name": "소프트웨어공학",
    "day": "MON",
    "startTime": "10:30",
    "endTime": "12:00",
    "buildingName": "신공학관",
    "roomNumber": "4142",
}


def without_id(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in c.items() if k != "id"} for c in courses]


async def add(client: AsyncClient, course: dict[str, Any], headers: dict = ALICE) -> dict:
    response = await client.post(COURSES, json=course, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def parse(client: AsyncClient, text: str = EXCEL_GRID) -> dict:
    response = await client.post("/api/v1/timetables/parse", json={"text": text}, headers=ALICE)
    assert response.status_code == 200
    return response.json()


# ---- 직접 입력 (기본) ----


async def test_add_course_minimal(client: AsyncClient) -> None:
    course = await add(
        client, {"name": "채플", "day": "WED", "startTime": "12:00", "endTime": "13:00"}
    )

    assert course["id"] is not None
    assert (course["buildingName"], course["floor"], course["location"]) == (None, None, None)


async def test_add_course_links_navigation(client: AsyncClient) -> None:
    course = await add(client, MANUAL)

    assert course["floor"] == 4
    # 신공학관 4층은 길안내 데이터가 있어서 층까지 안내한다
    assert course["location"]["precision"] == "FLOOR"
    assert course["location"]["placeName"] == "신공학관 4층"


async def test_add_course_with_alias_building(client: AsyncClient) -> None:
    course = await add(client, {**MANUAL, "buildingName": "신공"})

    assert course["location"]["buildingName"] == "신공학관"


async def test_list_is_sorted_by_day_and_time(client: AsyncClient) -> None:
    await add(client, {**MANUAL, "name": "목요일", "day": "THU"})
    await add(client, {**MANUAL, "name": "월요일 오후", "startTime": "15:00", "endTime": "16:00"})
    await add(client, MANUAL)

    response = await client.get(MINE, headers=ALICE)

    names = [c["name"] for c in response.json()["courses"]]
    assert names == ["소프트웨어공학", "월요일 오후", "목요일"]
    assert response.json()["updatedAt"] is not None


async def test_update_course(client: AsyncClient) -> None:
    course = await add(client, MANUAL)

    response = await client.put(
        f"{COURSES}/{course['id']}",
        json={**MANUAL, "day": "TUE", "buildingName": "혜화관", "roomNumber": "301"},
        headers=ALICE,
    )

    updated = response.json()
    assert response.status_code == 200
    assert updated["id"] == course["id"]
    assert (updated["day"], updated["floor"]) == ("TUE", 3)
    assert updated["location"]["buildingName"] == "혜화관"


async def test_delete_course(client: AsyncClient) -> None:
    keep = await add(client, MANUAL)
    gone = await add(client, {**MANUAL, "name": "지울 과목"})

    deleted = await client.delete(f"{COURSES}/{gone['id']}", headers=ALICE)
    response = await client.get(MINE, headers=ALICE)

    assert deleted.status_code == 204
    assert [c["id"] for c in response.json()["courses"]] == [keep["id"]]


async def test_other_users_course_is_not_found(client: AsyncClient) -> None:
    course = await add(client, MANUAL)

    updated = await client.put(f"{COURSES}/{course['id']}", json=MANUAL, headers=BOB)
    deleted = await client.delete(f"{COURSES}/{course['id']}", headers=BOB)
    bobs = await client.get(MINE, headers=BOB)

    assert updated.status_code == 404
    assert updated.json()["error"]["code"] == "COURSE_NOT_FOUND"
    assert deleted.status_code == 404
    assert bobs.json()["courses"] == []


@pytest.mark.parametrize(
    "bad",
    [
        {"endTime": "09:00"},  # 끝이 시작보다 빠름
        {"startTime": "25:00"},
        {"day": "월"},
        {"name": ""},
    ],
)
async def test_add_course_validation(client: AsyncClient, bad: dict[str, str]) -> None:
    response = await client.post(COURSES, json={**MANUAL, **bad}, headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_add_course_limit(client: AsyncClient) -> None:
    await client.put(MINE, json={"courses": [MANUAL] * MAX_COURSES}, headers=ALICE)

    response = await client.post(COURSES, json=MANUAL, headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOO_MANY_COURSES"


async def test_requires_login(client: AsyncClient) -> None:
    assert (await client.get(MINE)).status_code == 401
    assert (await client.post(COURSES, json=MANUAL)).status_code == 401


# ---- 엑셀 붙여넣기 (편의 기능) ----


async def test_parse_excel_paste(client: AsyncClient) -> None:
    body = await parse(client)

    assert body["warnings"] == []
    assert len(body["courses"]) == 10
    first = body["courses"][0]
    assert first["id"] is None
    assert first["name"] == "소프트웨어공학"
    assert (first["day"], first["startTime"], first["endTime"]) == ("MON", "10:30", "12:00")
    assert (first["roomNumber"], first["buildingName"], first["floor"]) == ("5145", "신공학관", 5)


async def test_parse_links_building_for_navigation(client: AsyncClient) -> None:
    body = await parse(client)

    location = body["courses"][0]["location"]
    assert location["buildingName"] == "신공학관"
    # 신공학관 5층은 아직 길안내 데이터가 없어서 건물까지만 안내한다
    assert location["precision"] == "BUILDING"
    assert location["placeName"] == "신공학관"
    assert location["placeId"] is not None


async def test_parse_does_not_save(client: AsyncClient) -> None:
    await parse(client)

    response = await client.get(MINE, headers=ALICE)
    assert response.json() == {"courses": [], "updatedAt": None}


async def test_parse_garbage_gives_warnings(client: AsyncClient) -> None:
    body = await parse(client, "아무 글자")

    assert body["courses"] == []
    assert body["warnings"]


async def test_parse_requires_login(client: AsyncClient) -> None:
    response = await client.post("/api/v1/timetables/parse", json={"text": EXCEL_GRID})

    assert response.status_code == 401


async def test_parse_empty_text_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/timetables/parse", json={"text": ""}, headers=ALICE)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_save_parsed_timetable(client: AsyncClient) -> None:
    preview = await parse(client)

    saved = await client.put(MINE, json={"courses": preview["courses"]}, headers=ALICE)
    mine = await client.get(MINE, headers=ALICE)

    assert saved.status_code == 200
    assert without_id(saved.json()["courses"]) == without_id(preview["courses"])
    assert all(c["id"] is not None for c in mine.json()["courses"])
    assert mine.json()["courses"] == saved.json()["courses"]


async def test_save_replaces_whole_timetable(client: AsyncClient) -> None:
    await add(client, {**MANUAL, "name": "직접 넣은 과목"})
    preview = await parse(client)

    await client.put(MINE, json={"courses": preview["courses"][:1]}, headers=ALICE)

    response = await client.get(MINE, headers=ALICE)
    assert [c["name"] for c in response.json()["courses"]] == ["소프트웨어공학"]


async def test_save_fills_room_fields_from_raw_room(client: AsyncClient) -> None:
    course = {
        "name": "엑셀 과목",
        "day": "FRI",
        "startTime": "09:00",
        "endTime": "10:30",
        "room": "301(혜화관 402-301 강의실)",
    }

    response = await client.put(MINE, json={"courses": [course]}, headers=ALICE)

    saved = response.json()["courses"][0]
    assert (saved["roomNumber"], saved["buildingName"], saved["floor"]) == ("301", "혜화관", 3)
    assert saved["location"]["buildingName"] == "혜화관"


async def test_timetables_are_per_user(client: AsyncClient) -> None:
    preview = await parse(client)
    await client.put(MINE, json={"courses": preview["courses"]}, headers=ALICE)

    response = await client.get(MINE, headers=BOB)

    assert response.json()["courses"] == []


async def test_delete_whole_timetable(client: AsyncClient) -> None:
    await add(client, MANUAL)

    deleted = await client.delete(MINE, headers=ALICE)
    response = await client.get(MINE, headers=ALICE)

    assert deleted.status_code == 204
    assert response.json()["courses"] == []


# ---- 길안내 장소 연결 ----


def test_locate_room_floor_with_data() -> None:
    location = locate_room("신공학관", 4)

    assert location is not None
    assert (location.precision, location.place_name) == ("FLOOR", "신공학관 4층")


def test_locate_room_unknown_building() -> None:
    assert locate_room("없는건물", 1) is None
    assert locate_room(None, 1) is None
