import math
import re
from datetime import datetime, timedelta, timezone

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.common.exceptions import AppException, NotFoundException
from app.programs.navigation import service as navigation
from app.programs.navigation.schemas import RouteMode
from app.timetable import repository
from app.timetable.models import TimetableCourse
from app.timetable.parser import parse_pasted_timetable, parse_room
from app.timetable.schemas import (
    MAX_COURSES,
    Course,
    CourseInput,
    NextCourseResponse,
    NextOrigin,
    OriginSource,
    ParseTimetableResponse,
    SaveTimetableRequest,
    TimetableResponse,
)

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 +9시간
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")  # datetime.weekday() 순서
DAY_KO = dict(zip(DAYS, "월화수목금토일", strict=True))

# 동국대 호실 번호는 앞자리가 층이다. 예: 5145 → 5층, 301 → 3층, B101 → 지하 1층
ROOM_FLOOR = re.compile(r"^(?P<basement>B?)(?P<floor>[1-9])\d{2,3}$", re.IGNORECASE)


def guess_floor(room_number: str | None) -> int | None:
    match = ROOM_FLOOR.match(room_number or "")
    if match is None:
        return None
    floor = int(match["floor"])
    return -floor if match["basement"] else floor


FIELD_LABELS = {
    "name": "과목명",
    "day": "요일",
    "start_time": "시작 시간",
    "end_time": "끝 시간",
    "building_name": "건물",
    "room_number": "호실",
    "room_description": "강의실 설명",
    "weeks": "주차",
    "room": "강의실",
}


def validation_message(exc: ValidationError) -> str:
    """Pydantic 검증 오류를 사람이 읽을 문장으로 바꾼다."""
    parts = []
    for error in exc.errors(include_url=False):
        field = str(error["loc"][0]) if error["loc"] else ""
        label = FIELD_LABELS.get(field, field)
        if error["type"] == "string_too_long":
            max_length = (error.get("ctx") or {}).get("max_length")
            parts.append(f"{label}은(는) {max_length}자 이하여야 합니다")
        elif label:
            parts.append(f"{label}: {error['msg']}")
        else:
            parts.append(str(error["msg"]).removeprefix("Value error, "))
    return ", ".join(parts)


def _filled(course: CourseInput) -> CourseInput:
    """엑셀 강의실 원문만 있고 건물·호실이 비어 있으면 원문에서 채운다."""
    if course.room and not (course.room_number or course.building_name):
        number, building, description = parse_room(course.room)
        return course.model_copy(
            update={
                "room_number": number,
                "building_name": building,
                "room_description": course.room_description or description,
            }
        )
    return course


def _checked(course: CourseInput, label: str = "") -> CourseInput:
    """원문에서 채운 값까지 포함해 다시 검증한다. 실패하면 400이고, 아무것도 저장하지 않는다.

    model_copy는 검증을 하지 않아서, 원문에서 뽑은 호실·건물·설명이 길이 제한을 넘을 수 있다.
    """
    try:
        return CourseInput.model_validate(_filled(course).model_dump())
    except ValidationError as exc:
        raise AppException(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"{label}{validation_message(exc)}",
        ) from exc


def _to_course(course: CourseInput, course_id: int | None = None) -> Course:
    floor = guess_floor(course.room_number)
    return Course(
        **course.model_dump(),
        id=course_id,
        floor=floor,
        location=navigation.locate_room(course.building_name, floor),
    )


def _from_model(model: TimetableCourse) -> Course:
    course = CourseInput.model_validate(model, from_attributes=True)
    return _to_course(course, model.id)


def _too_many() -> AppException:
    return AppException(
        status.HTTP_400_BAD_REQUEST,
        "TOO_MANY_COURSES",
        f"시간표에는 수업을 {MAX_COURSES}개까지 넣을 수 있습니다.",
    )


async def _get_own_course(session: AsyncSession, user: User, course_id: int) -> TimetableCourse:
    course = await repository.get_course(session, user.id, course_id)
    if course is None:
        raise NotFoundException("COURSE_NOT_FOUND", "수업을 찾을 수 없습니다.")
    return course


# ---- 조회 ----


async def get_timetable(session: AsyncSession, user: User) -> TimetableResponse:
    models = await repository.list_courses(session, user.id)
    return TimetableResponse(
        courses=[_from_model(m) for m in models],
        updated_at=max((m.updated_at for m in models), default=None),
    )


# ---- 직접 입력 (수업 하나씩) ----


async def add_course(session: AsyncSession, user: User, body: CourseInput) -> Course:
    if await repository.count_courses(session, user.id) >= MAX_COURSES:
        raise _too_many()
    model = TimetableCourse(user_id=user.id, **_checked(body).model_dump())
    return _from_model(await repository.add_course(session, model))


async def update_course(
    session: AsyncSession, user: User, course_id: int, body: CourseInput
) -> Course:
    model = await _get_own_course(session, user, course_id)
    values = _checked(body).model_dump()  # 검증을 먼저 끝내고 바꾼다
    updated = await repository.update_course(session, model, values)
    return _from_model(updated)


async def delete_course(session: AsyncSession, user: User, course_id: int) -> None:
    model = await _get_own_course(session, user, course_id)
    await repository.delete_course(session, model)


# ---- 엑셀 붙여넣기 (편의 기능) ----


def parse_timetable(text: str) -> ParseTimetableResponse:
    """붙여넣은 엑셀 시간표를 읽어 미리보기로 돌려준다. 저장하지 않는다."""
    result = parse_pasted_timetable(text)
    warnings = list(result.warnings)
    courses = []
    # 수업 단위로 검증해서, 잘못된 수업은 빼고 경고로 알린다 (나머지 수업은 그대로 보여 준다).
    for c in result.courses:
        try:
            course = CourseInput(
                name=c.name[:100],
                day=c.day,  # type: ignore[arg-type]  # 파서가 MON~SUN만 만든다
                start_time=c.start_time,
                end_time=c.end_time,
                weeks=c.weeks,
                room=c.room,
                room_number=c.room_number,
                building_name=c.building_name,
                room_description=c.room_description,
            )
        except ValidationError as exc:
            when = f"{DAY_KO.get(c.day, c.day)} {c.start_time}~{c.end_time}"
            warnings.append(
                f"{when} '{c.name[:30]}' 수업을 건너뛰었습니다: {validation_message(exc)}"
            )
            continue
        courses.append(_to_course(course))
    return ParseTimetableResponse(courses=courses, warnings=warnings)


async def save_timetable(
    session: AsyncSession, user: User, body: SaveTimetableRequest
) -> TimetableResponse:
    """시간표 전체를 한 번에 바꾼다. 엑셀 미리보기를 확인한 뒤 등록할 때 쓴다.

    모든 수업을 먼저 검증한다. 하나라도 틀리면 400이고, 기존 시간표는 그대로 둔다.
    """
    checked = [_checked(course, f"{i}번째 수업: ") for i, course in enumerate(body.courses, 1)]
    models = [TimetableCourse(user_id=user.id, **course.model_dump()) for course in checked]
    await repository.replace_courses(session, user.id, models)
    return await get_timetable(session, user)


async def delete_timetable(session: AsyncSession, user: User) -> None:
    await repository.delete_courses(session, user.id)


# ---- 다음 수업 (AI 없이 현재 시간으로 판단) ----


def now_kst() -> datetime:
    return datetime.now(KST)


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _place_of(course: Course | None) -> tuple[int, str] | None:
    location = course.location if course else None
    if location and location.place_id is not None and location.place_name:
        return location.place_id, location.place_name
    return None


def _where(course: Course) -> str:
    parts = [p for p in (course.building_name, course.room_number) if p]
    return " ".join(parts) or "강의실 미정"


def _after(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours == 0:
        return f"{rest}분 후"
    return f"{hours}시간 {rest}분 후" if rest else f"{hours}시간 후"


def _when(course: Course, days_ahead: int, starts_in: int) -> str:
    if days_ahead == 0:
        return f"오늘 {course.start_time} ({_after(starts_in)})"
    if days_ahead == 1:
        return f"내일({DAY_KO[course.day]}) {course.start_time}"
    return f"{DAY_KO[course.day]}요일 {course.start_time}"


def _find_next(courses: list[Course], now: datetime) -> tuple[Course | None, int, int]:
    """(다음 수업, 며칠 뒤, 남은 분). 오늘 남은 수업부터 일주일 뒤 같은 요일까지 찾는다."""
    now_min = now.hour * 60 + now.minute
    for days_ahead in range(8):
        day = DAYS[(now.weekday() + days_ahead) % 7]
        candidates = [
            c
            for c in courses
            if c.day == day and (days_ahead > 0 or _minutes(c.start_time) > now_min)
        ]
        if candidates:
            course = min(candidates, key=lambda c: _minutes(c.start_time))
            return course, days_ahead, days_ahead * 24 * 60 + _minutes(course.start_time) - now_min
    return None, 0, 0


async def next_course(
    session: AsyncSession,
    user: User,
    now: datetime,
    from_place_id: int | None = None,
    mode: RouteMode = "FASTEST",
    avoid_stairs: bool = False,
) -> NextCourseResponse:
    """지금 시간과 시간표로 다음 수업을 찾고, 출발지를 정할 수 있으면 경로도 만든다.

    출발지: 요청한 장소 > 지금 듣는 수업 강의실 > 오늘 직전 수업 강의실 (다음 수업이 오늘일 때만).
    GPS가 없어서 이 순서로 정하고, 못 정하면 경로 없이 돌려준다.
    """
    now = now.astimezone(KST)
    courses = (await get_timetable(session, user)).courses
    empty = NextCourseResponse(
        now=now,
        current=None,
        next=None,
        starts_in_minutes=None,
        origin=None,
        route=None,
        route_error=None,
        message="등록된 시간표가 없습니다.",
    )
    if not courses:
        return empty

    now_min = now.hour * 60 + now.minute
    today = [c for c in courses if c.day == DAYS[now.weekday()]]
    current = max(
        (c for c in today if _minutes(c.start_time) <= now_min < _minutes(c.end_time)),
        key=lambda c: _minutes(c.start_time),
        default=None,
    )
    previous = max(
        (c for c in today if _minutes(c.end_time) <= now_min),
        key=lambda c: _minutes(c.end_time),
        default=None,
    )
    upcoming, days_ahead, starts_in = _find_next(courses, now)
    if upcoming is None:
        return empty

    origin: NextOrigin | None = None
    origin_course: Course | None = None  # 출발지가 수업 강의실일 때 그 수업 (층 비교용)
    if from_place_id is not None:
        place = navigation.get_place(from_place_id)
        if place is None:
            raise NotFoundException(
                "PLACE_NOT_FOUND", f"존재하지 않는 장소입니다. ({from_place_id})"
            )
        origin = NextOrigin(place_id=place.id, place_name=place.name, source="REQUEST")
    elif days_ahead == 0:
        sources: tuple[tuple[Course | None, OriginSource], ...] = (
            (current, "CURRENT_CLASS"),
            (previous, "PREVIOUS_CLASS"),
        )
        for course, source in sources:
            found = _place_of(course)
            if found:
                origin = NextOrigin(place_id=found[0], place_name=found[1], source=source)
                origin_course = course
                break

    route = None
    route_error: str | None = None
    destination = _place_of(upcoming)
    if destination is None:
        route_error = "NO_LOCATION"
    elif origin is not None:
        if origin.place_id == destination[0]:
            # 같은 장소(보통 같은 건물 마커)라도 층이 다르면 층 사이를 옮겨야 한다.
            # 그 층들의 길안내 데이터가 없어서 같은 마커로 묶인 것이므로 안내할 수 없다고 알린다.
            from_floor = origin_course.floor if origin_course else None
            moves_floor = None not in (from_floor, upcoming.floor) and from_floor != upcoming.floor
            route_error = "FLOOR_ROUTE_UNAVAILABLE" if moves_floor else "SAME_PLACE"
        else:
            try:
                route = navigation.route_between(
                    origin.place_id, destination[0], mode=mode, avoid_stairs=avoid_stairs
                )
            except AppException as exc:
                route_error = exc.code

    parts = []
    if current:
        parts.append(f"지금 수업: {current.name} ({current.end_time}까지)")
    parts.append(
        f"다음 수업: {_when(upcoming, days_ahead, starts_in)} {upcoming.name} · {_where(upcoming)}"
    )
    building = upcoming.location.building_name if upcoming.location else ""
    if route:
        minutes = max(1, math.ceil(route.summary.total_seconds / 60))
        parts.append(f"{origin.place_name if origin else ''}에서 걸어서 약 {minutes}분")
        if upcoming.location and upcoming.location.precision == "BUILDING" and upcoming.floor:
            label = navigation.floor_label(upcoming.floor)
            parts.append(f"{label} 안내 데이터가 없어 {building}까지 안내합니다")
    elif route_error == "FLOOR_ROUTE_UNAVAILABLE" and origin_course is not None:
        parts.append(
            f"같은 건물({building}) {navigation.floor_label(origin_course.floor or 0)} → "
            f"{navigation.floor_label(upcoming.floor or 0)} 이동이에요. "
            "층 사이 길안내 데이터는 아직 없습니다"
        )
    elif route_error == "SAME_PLACE":
        parts.append("같은 곳에서 이어지는 수업입니다")
    elif route_error == "NO_LOCATION":
        parts.append("강의실 건물을 몰라 길안내를 할 수 없습니다")
    elif origin is None:
        parts.append("출발지를 고르면 길을 알려 드립니다")

    return NextCourseResponse(
        now=now,
        current=current,
        next=upcoming,
        starts_in_minutes=starts_in,
        origin=origin,
        route=route,
        route_error=route_error,
        message=" · ".join(parts),
    )
