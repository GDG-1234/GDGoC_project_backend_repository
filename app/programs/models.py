from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class StoredToolResult(Base):
    """tool 결과의 화면용 데이터(ui). 채팅 창구가 resultId로 꺼내 카드로 붙인다.

    Cloud Run 인스턴스가 여러 대여도 같은 데이터를 보도록 DB에 둔다. 보관 시간이 지나면 지운다.
    """

    __tablename__ = "tool_results"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # r_<uuid hex>
    tool_name: Mapped[str] = mapped_column(String(64))
    ui: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
