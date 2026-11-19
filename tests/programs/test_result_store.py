import pytest

from app.programs.result_store import MemoryResultStore


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
