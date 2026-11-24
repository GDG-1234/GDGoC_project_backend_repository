from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import CurrentUser, SessionDep
from app.programs.navigation.schemas import RouteMode
from app.timetable import service
from app.timetable.schemas import (
    Course,
    CourseInput,
    NextCourseResponse,
    ParseTimetableRequest,
    ParseTimetableResponse,
    SaveTimetableRequest,
    TimetableResponse,
)

router = APIRouter(prefix="/api/v1/timetables", tags=["timetable"])


# ---- 조회 ----


@router.get(
    "/me",
    response_model=TimetableResponse,
    status_code=status.HTTP_200_OK,
    summary="내 시간표",
)
async def read_my_timetable(user: CurrentUser, session: SessionDep) -> TimetableResponse:
    return await service.get_timetable(session, user)


@router.get(
    "/me/next",
    response_model=NextCourseResponse,
    status_code=status.HTTP_200_OK,
    summary="다음 수업과 가는 길 (현재 시간 기준)",
)
async def read_next_course(
    user: CurrentUser,
    session: SessionDep,
    now: Annotated[datetime, Depends(service.now_kst)],
    from_place_id: Annotated[
        int | None,
        Query(alias="fromPlaceId", gt=0, description="출발 장소. 없으면 지금·직전 수업 강의실"),
    ] = None,
    mode: Annotated[RouteMode, Query()] = "FASTEST",
    avoid_stairs: Annotated[bool, Query(alias="avoidStairs")] = False,
) -> NextCourseResponse:
    return await service.next_course(session, user, now, from_place_id, mode, avoid_stairs)


# ---- 직접 입력 (수업 하나씩) ----


@router.post(
    "/me/courses",
    response_model=Course,
    status_code=status.HTTP_201_CREATED,
    summary="수업 하나 추가",
)
async def add_course(body: CourseInput, user: CurrentUser, session: SessionDep) -> Course:
    return await service.add_course(session, user, body)


@router.put(
    "/me/courses/{course_id}",
    response_model=Course,
    status_code=status.HTTP_200_OK,
    summary="수업 하나 수정",
)
async def update_course(
    course_id: int, body: CourseInput, user: CurrentUser, session: SessionDep
) -> Course:
    return await service.update_course(session, user, course_id, body)


@router.delete(
    "/me/courses/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="수업 하나 삭제",
)
async def delete_course(course_id: int, user: CurrentUser, session: SessionDep) -> None:
    await service.delete_course(session, user, course_id)


# ---- 엑셀 붙여넣기 (편의 기능) ----


@router.post(
    "/parse",
    response_model=ParseTimetableResponse,
    status_code=status.HTTP_200_OK,
    summary="붙여넣은 엑셀 시간표 읽기 (저장하지 않음, 미리보기용)",
)
async def parse_timetable(body: ParseTimetableRequest, _: CurrentUser) -> ParseTimetableResponse:
    return service.parse_timetable(body.text)


@router.put(
    "/me",
    response_model=TimetableResponse,
    status_code=status.HTTP_200_OK,
    summary="시간표 전체를 한 번에 바꾸기 (엑셀 미리보기 확인 후 등록)",
)
async def save_my_timetable(
    body: SaveTimetableRequest, user: CurrentUser, session: SessionDep
) -> TimetableResponse:
    return await service.save_timetable(session, user, body)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="내 시간표 전체 지우기",
)
async def delete_my_timetable(user: CurrentUser, session: SessionDep) -> None:
    await service.delete_timetable(session, user)
