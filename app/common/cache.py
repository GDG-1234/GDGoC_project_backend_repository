"""외부 사이트에서 읽은 결과를 잠깐 보관하는 메모리 캐시.

신선한 동안은 저장된 값을 준다. 만료되면 다시 읽고, 다시 읽기가 실패하면
`stale_seconds` 안의 오래된 값이라도 `stale=True`로 준다. 실패는 저장하지 않는다.
인스턴스마다 따로 동작한다 (Cloud Run 인스턴스끼리 공유하지 않음).

같은 키를 동시에 요청하면 읽기는 한 번만 하고, 그 결과(성공이든 실패든)를 모두가 나눠 받는다.
요청한 쪽이 시간 초과로 취소돼도 읽기는 끝까지 가서 결과를 저장한다.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheResult[T]:
    value: T
    stale: bool


def _consume_exception(task: asyncio.Task[object]) -> None:
    # 기다리던 요청이 모두 취소돼도 "exception was never retrieved" 경고가 나지 않게 한다
    if not task.cancelled():
        task.exception()


class TtlCache[T]:
    def __init__(
        self,
        fresh_seconds: float,
        stale_seconds: float = 86_400,
        max_items: int = 500,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fresh_seconds = fresh_seconds
        self._stale_seconds = stale_seconds
        self._max_items = max_items
        self._clock = clock
        self._items: dict[str, tuple[T, float]] = {}
        self._loading: dict[str, asyncio.Task[T]] = {}

    async def get_or_load(self, key: str, loader: Callable[[], Awaitable[T]]) -> CacheResult[T]:
        item = self._items.get(key)
        if item is not None and self._clock() - item[1] < self._fresh_seconds:
            return CacheResult(item[0], stale=False)

        task = self._loading.get(key)
        if task is None:
            task = asyncio.ensure_future(self._load(key, loader))
            task.add_done_callback(_consume_exception)
            self._loading[key] = task
        try:
            # shield: 이 요청이 취소돼도 다른 요청이 기다리는 읽기는 계속된다
            value = await asyncio.shield(task)
        except Exception:
            item = self._items.get(key)
            if item is not None and self._clock() - item[1] <= self._stale_seconds:
                return CacheResult(item[0], stale=True)
            raise
        return CacheResult(value, stale=False)

    async def _load(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        try:
            value = await loader()
            self._store(key, value)
            return value
        finally:
            self._loading.pop(key, None)

    def _store(self, key: str, value: T) -> None:
        self._items.pop(key, None)
        self._items[key] = (value, self._clock())
        while len(self._items) > self._max_items:
            # dict는 넣은 순서를 지키므로 맨 앞이 가장 오래 저장된 항목이다
            del self._items[next(iter(self._items))]
