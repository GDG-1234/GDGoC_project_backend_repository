import asyncio

import anyio
import pytest

from app.common.cache import CacheResult, TtlCache

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Loader:
    """부를 때마다 호출 수를 세고, 정해 둔 값이나 예외를 낸다."""

    def __init__(self, value: str = "a") -> None:
        self.value = value
        self.error: Exception | None = None
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.value


@pytest.fixture
def clock() -> Clock:
    return Clock()


async def test_fresh_value_is_reused(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    loader = Loader()

    await cache.get_or_load("k", loader)
    result = await cache.get_or_load("k", loader)

    assert loader.calls == 1
    assert result == CacheResult("a", stale=False)


async def test_reload_after_fresh_expires(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    loader = Loader()
    await cache.get_or_load("k", loader)

    clock.now = 11
    loader.value = "b"
    result = await cache.get_or_load("k", loader)

    assert loader.calls == 2
    assert result == CacheResult("b", stale=False)


async def test_stale_value_when_reload_fails(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    loader = Loader()
    await cache.get_or_load("k", loader)

    clock.now = 11
    loader.error = RuntimeError("down")
    result = await cache.get_or_load("k", loader)

    assert result == CacheResult("a", stale=True)


async def test_raise_when_reload_fails_and_too_old(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, stale_seconds=100, clock=clock)
    loader = Loader()
    await cache.get_or_load("k", loader)

    clock.now = 200
    loader.error = RuntimeError("down")
    with pytest.raises(RuntimeError):
        await cache.get_or_load("k", loader)


async def test_raise_when_first_load_fails(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    loader = Loader()
    loader.error = RuntimeError("down")

    with pytest.raises(RuntimeError):
        await cache.get_or_load("k", loader)


async def test_failure_is_not_cached(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    loader = Loader()
    loader.error = RuntimeError("down")
    with pytest.raises(RuntimeError):
        await cache.get_or_load("k", loader)

    loader.error = None
    result = await cache.get_or_load("k", loader)

    assert loader.calls == 2
    assert result == CacheResult("a", stale=False)


async def test_oldest_evicted_over_max_items(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, max_items=2, clock=clock)
    loader = Loader()
    for key in ("a", "b", "c"):
        await cache.get_or_load(key, loader)
    assert loader.calls == 3

    await cache.get_or_load("c", loader)
    assert loader.calls == 3  # c는 남아 있다
    await cache.get_or_load("a", loader)
    assert loader.calls == 4  # a는 지워졌다


async def test_concurrent_requests_during_outage_all_get_stale(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    calls = 0

    async def loader() -> str:
        nonlocal calls
        calls += 1
        if calls > 1:
            await anyio.sleep(0.01)
            raise RuntimeError("down")
        return "a"

    await cache.get_or_load("k", loader)
    clock.now = 11

    results = await asyncio.gather(*(cache.get_or_load("k", loader) for _ in range(4)))

    assert calls == 2  # 처음 1번 + 다시 읽기 1번 (기다린 요청들은 같은 실패를 나눠 받는다)
    assert all(r == CacheResult("a", stale=True) for r in results)


async def test_caller_timeout_does_not_cancel_shared_load(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    calls = 0

    async def slow_loader() -> str:
        nonlocal calls
        calls += 1
        await anyio.sleep(0.05)
        return "a"

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(cache.get_or_load("k", slow_loader), timeout=0.01)
    await anyio.sleep(0.1)

    result = await cache.get_or_load("k", slow_loader)

    assert calls == 1  # 첫 호출이 취소돼도 읽기는 끝까지 가서 저장됐다
    assert result == CacheResult("a", stale=False)


async def test_concurrent_misses_load_once(clock: Clock) -> None:
    cache: TtlCache[str] = TtlCache(fresh_seconds=10, clock=clock)
    calls = 0

    async def slow_loader() -> str:
        nonlocal calls
        calls += 1
        await anyio.sleep(0.01)
        return "a"

    results = await asyncio.gather(*(cache.get_or_load("k", slow_loader) for _ in range(5)))

    assert calls == 1
    assert all(r.value == "a" for r in results)
