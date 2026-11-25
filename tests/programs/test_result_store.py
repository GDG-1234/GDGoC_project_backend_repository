from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.programs.result_store import DbResultStore, MemoryResultStore


class FakeClock:
    """테스트에서 시간을 직접 움직이기 위한 가짜 시계."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.anyio
async def test_put_then_get_returns_stored_ui() -> None:
    store = MemoryResultStore(ttl_seconds=60, max_items=10, clock=FakeClock())

    result_id = await store.put("demo.hello", {"card": "안녕"})
    stored = await store.get(result_id)

    assert result_id.startswith("r_")
    assert stored is not None
    assert stored.tool_name == "demo.hello"
    assert stored.ui == {"card": "안녕"}


@pytest.mark.anyio
async def test_unknown_id_returns_none() -> None:
    store = MemoryResultStore(ttl_seconds=60, max_items=10)

    assert await store.get("r_unknown") is None


@pytest.mark.anyio
async def test_expired_result_returns_none() -> None:
    clock = FakeClock()
    store = MemoryResultStore(ttl_seconds=60, max_items=10, clock=clock)
    result_id = await store.put("demo.hello", {"card": "안녕"})

    clock.now = 59.9
    assert await store.get(result_id) is not None

    clock.now = 60
    assert await store.get(result_id) is None


@pytest.mark.anyio
async def test_oldest_is_removed_when_full() -> None:
    store = MemoryResultStore(ttl_seconds=60, max_items=2, clock=FakeClock())

    first = await store.put("demo.a", {"n": 1})
    second = await store.put("demo.b", {"n": 2})
    third = await store.put("demo.c", {"n": 3})

    assert await store.get(first) is None
    assert await store.get(second) is not None
    assert await store.get(third) is not None


@pytest.mark.anyio
async def test_expired_results_are_cleaned_on_put() -> None:
    clock = FakeClock()
    store = MemoryResultStore(ttl_seconds=60, max_items=2, clock=clock)
    await store.put("demo.a", {"n": 1})
    await store.put("demo.b", {"n": 2})

    clock.now = 100
    fresh = await store.put("demo.c", {"n": 3})
    newer = await store.put("demo.d", {"n": 4})

    assert await store.get(fresh) is not None
    assert await store.get(newer) is not None


# ---- DB 보관 (운영 기본값) ----


class FakeUtcClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_db_store_put_then_get(session: AsyncSession) -> None:
    store = DbResultStore(session, ttl_seconds=60, clock=FakeUtcClock())

    result_id = await store.put("navigation_find_route", {"route": {"steps": []}})
    stored = await store.get(result_id)

    assert result_id.startswith("r_")
    assert stored is not None
    assert (stored.tool_name, stored.ui) == ("navigation_find_route", {"route": {"steps": []}})


@pytest.mark.anyio
async def test_db_store_is_shared_between_store_objects(session: AsyncSession) -> None:
    # 인스턴스가 달라도(여기서는 store 객체가 달라도) 같은 DB면 찾는다
    clock = FakeUtcClock()
    result_id = await DbResultStore(session, ttl_seconds=60, clock=clock).put("t_a", {"a": 1})

    stored = await DbResultStore(session, ttl_seconds=60, clock=clock).get(result_id)

    assert stored is not None and stored.ui == {"a": 1}


@pytest.mark.anyio
async def test_db_store_expires_and_cleans_up(session: AsyncSession) -> None:
    clock = FakeUtcClock()
    store = DbResultStore(session, ttl_seconds=60, clock=clock)
    old_id = await store.put("t_a", {"a": 1})

    clock.now += timedelta(seconds=61)
    assert await store.get(old_id) is None

    await store.put("t_b", {"b": 1})  # 넣을 때 만료된 결과를 지운다
    clock.now -= timedelta(seconds=61)  # 시간을 되돌려도 이미 지워져 있다
    assert await store.get(old_id) is None


@pytest.mark.anyio
async def test_db_store_unknown_id(session: AsyncSession) -> None:
    store = DbResultStore(session, ttl_seconds=60, clock=FakeUtcClock())

    assert await store.get("r_없음") is None
