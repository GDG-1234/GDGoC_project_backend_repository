import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredResult:
    result_id: str
    tool_name: str
    ui: dict[str, Any]
    created_at: float


class ResultStore(Protocol):
    async def put(self, tool_name: str, ui: dict[str, Any]) -> str: ...

    async def get(self, result_id: str) -> StoredResult | None: ...


class MemoryResultStore:
    """메모리에 ui를 잠시 보관한다. 서버를 재시작하면 사라진다."""

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
        result_id = f"r_{uuid.uuid4().hex}"
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
