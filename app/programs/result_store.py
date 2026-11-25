import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.programs.models import StoredToolResult, utc_now


@dataclass(frozen=True)
class StoredResult:
    result_id: str
    tool_name: str
    ui: dict[str, Any]
    created_at: float


class ResultStore(Protocol):
    async def put(self, tool_name: str, ui: dict[str, Any]) -> str: ...

    async def get(self, result_id: str) -> StoredResult | None: ...


def _new_result_id() -> str:
    return f"r_{uuid.uuid4().hex}"


class DbResultStore:
    """DB에 ui를 보관한다 (운영 기본값).

    tool 실행 요청(AI 서비스)과 채팅 요청(사용자)이 서로 다른 Cloud Run 인스턴스에서
    처리돼도 같은 결과를 찾을 수 있다. 보관 시간이 지난 결과는 새로 넣을 때 지운다.
    """

    def __init__(
        self,
        session: AsyncSession,
        ttl_seconds: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock

    async def put(self, tool_name: str, ui: dict[str, Any]) -> str:
        now = self._clock()
        await self._session.execute(
            delete(StoredToolResult).where(StoredToolResult.created_at < now - self._ttl)
        )
        result_id = _new_result_id()
        self._session.add(
            StoredToolResult(id=result_id, tool_name=tool_name, ui=ui, created_at=now)
        )
        await self._session.commit()
        return result_id

    async def get(self, result_id: str) -> StoredResult | None:
        result = await self._session.execute(
            select(StoredToolResult).where(StoredToolResult.id == result_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        created_at = row.created_at
        if created_at.tzinfo is None:  # SQLite는 시간대 없이 돌려준다 (저장은 UTC)
            created_at = created_at.replace(tzinfo=self._clock().tzinfo)
        if self._clock() - created_at >= self._ttl:
            return None
        return StoredResult(row.id, row.tool_name, row.ui, created_at.timestamp())


class MemoryResultStore:
    """메모리에 ui를 잠시 보관한다. 서버를 재시작하면 사라진다 (테스트용)."""

    def __init__(
        self,
        ttl_seconds: float,
        max_items: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_items = max_items
        self._clock = clock
        self._items: OrderedDict[str, StoredResult] = OrderedDict()

    async def put(self, tool_name: str, ui: dict[str, Any]) -> str:
        self._remove_expired()
        while len(self._items) >= self._max_items:
            self._items.popitem(last=False)
        result_id = _new_result_id()
        self._items[result_id] = StoredResult(result_id, tool_name, ui, self._clock())
        return result_id

    async def get(self, result_id: str) -> StoredResult | None:
        item = self._items.get(result_id)
        if item is None:
            return None
        if self._is_expired(item):
            del self._items[result_id]
            return None
        return item

    def _is_expired(self, item: StoredResult) -> bool:
        return self._clock() - item.created_at >= self._ttl

    def _remove_expired(self) -> None:
        # 넣은 순서대로 쌓이므로 앞에서부터 만료된 것만 지우면 된다.
        while self._items:
            oldest = next(iter(self._items.values()))
            if not self._is_expired(oldest):
                break
            self._items.popitem(last=False)
