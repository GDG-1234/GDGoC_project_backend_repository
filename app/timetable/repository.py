from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.timetable.models import TimetableCourse

DAY_ORDER = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


async def list_courses(session: AsyncSession, user_id: int) -> list[TimetableCourse]:
    result = await session.execute(
        select(TimetableCourse).where(TimetableCourse.user_id == user_id)
    )
    courses = list(result.scalars().all())
    courses.sort(key=lambda c: (DAY_ORDER.get(c.day, 7), c.start_time, c.name))
    return courses


async def count_courses(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(TimetableCourse).where(TimetableCourse.user_id == user_id)
    )
    return result.scalar_one()


async def get_course(session: AsyncSession, user_id: int, course_id: int) -> TimetableCourse | None:
    """남의 수업은 없는 것으로 본다 (user_id까지 맞아야 찾는다)."""
    result = await session.execute(
        select(TimetableCourse).where(
            TimetableCourse.id == course_id, TimetableCourse.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def add_course(session: AsyncSession, course: TimetableCourse) -> TimetableCourse:
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return course


async def update_course(
    session: AsyncSession, course: TimetableCourse, values: dict[str, object]
) -> TimetableCourse:
    for key, value in values.items():
        setattr(course, key, value)
    await session.commit()
    await session.refresh(course)
    return course


async def delete_course(session: AsyncSession, course: TimetableCourse) -> None:
    await session.delete(course)
    await session.commit()


async def replace_courses(
    session: AsyncSession, user_id: int, courses: Sequence[TimetableCourse]
) -> None:
    """시간표를 통째로 바꾼다 (기존 수업을 지우고 새로 넣는다)."""
    await session.execute(delete(TimetableCourse).where(TimetableCourse.user_id == user_id))
    session.add_all(courses)
    await session.commit()


async def delete_courses(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(TimetableCourse).where(TimetableCourse.user_id == user_id))
    await session.commit()
