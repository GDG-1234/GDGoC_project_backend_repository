from pathlib import Path

import anyio
import httpx
import pytest

from app.common.cache import TtlCache
from app.programs.cafeteria import source

FIXTURES = Path(__file__).parent / "fixtures"

SDAY_19 = 1795014000  # 2026-11-19(목) 0시 KST
SDAY_22 = 1795273200  # 2026-11-22(일) 0시 KST


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture
def html_19() -> str:
    """2026-11-19(목) 날짜별 식단 페이지. 상록원 1~3층 영업."""
    return fixture_bytes("cafeteria_2026-11-19.html").decode("cp949")


@pytest.fixture
def html_22() -> str:
    """2026-11-22(일) 날짜별 식단 페이지. 모두 휴무."""
    return fixture_bytes("cafeteria_2026-11-22.html").decode("cp949")


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeCoop:
    """생협 사이트 흉내. `sday`에 맞는 저장 페이지를 돌려준다."""

    def __init__(self) -> None:
        self.pages = {
            SDAY_19: fixture_bytes("cafeteria_2026-11-19.html"),
            SDAY_22: fixture_bytes("cafeteria_2026-11-22.html"),
        }
        self.down = False
        self.broken = False
        self.requests = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.down:
            raise httpx.ConnectTimeout("timed out", request=request)
        if self.broken:
            return httpx.Response(200, content=b"<html><body></body></html>")
        return httpx.Response(200, content=self.pages[int(request.url.params["sday"])])

    async def slow_handler(self, request: httpx.Request) -> httpx.Response:
        """응답이 1초 걸린다 (전체 시간 제한 테스트용)."""
        await anyio.sleep(1)
        return self.handler(request)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def coop(monkeypatch: pytest.MonkeyPatch, clock: Clock) -> FakeCoop:
    """학교 사이트 대신 FakeCoop을 쓰고, 테스트마다 빈 캐시(가짜 시계)로 시작한다."""
    fake = FakeCoop()
    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(
        source, "day_menu_cache", TtlCache(fresh_seconds=source.FRESH_SECONDS, clock=clock)
    )
    return fake
