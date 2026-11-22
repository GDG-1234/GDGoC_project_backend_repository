from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimetableCourse(Base):
    """사용자 시간표의 수업 하나 (요일 + 시간 한 덩어리).

    직접 입력은 한 개씩 추가·수정·삭제하고, 엑셀 붙여넣기는 시간표 전체를 한 번에 바꾼다.
    """

    __tablename__ = "timetable_courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    day: Mapped[str] = mapped_column(String(3))  # MON ~ SUN
    start_time: Mapped[str] = mapped_column(String(5))  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5))  # HH:MM
    weeks: Mapped[str | None] = mapped_column(String(50))  # 예: 1주차~15주차
    room: Mapped[str | None] = mapped_column(String(200))  # 강의실 칸 원문
    room_number: Mapped[str | None] = mapped_column(String(20))  # 예: 5145
    building_name: Mapped[str | None] = mapped_column(String(100))  # 예: 신공학관
    room_description: Mapped[str | None] = mapped_column(String(100))  # 예: 실습실4
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
