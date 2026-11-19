import datetime as dt

import anyio
import httpx
import pytest

from app.programs.cafeteria import source
from app.programs.cafeteria.source import (
    BASE_URL,
    PageFormatError,
    day_url,
    fetch_day_page,
    parse_day_page,
)
from tests.programs.cafeteria.conftest import fixture_bytes


def test_day_url() -> None:
    assert day_url(dt.date(2026, 11, 19)) == f"{BASE_URL}?w=4&l=1&sday=1795014000"
    assert day_url(dt.date(2026, 11, 16)).endswith("sday=1794754800")


def test_parse_weekday_page(html_19: str) -> None:
    menu = parse_day_page(html_19, dt.date(2026, 11, 19))

    assert menu.date == dt.date(2026, 11, 19)
    # 주석 안 식당(그루터기 등)과 일산 식당이 없다
    assert [c.name for c in menu.cafeterias] == [
        "상록원3층식당",
        "상록원2층식당",
        "상록원1층식당(솥앤누들)",
    ]
    third, second, first = menu.cafeterias
    assert [(m.meal, m.corner) for m in third.meals] == [
        ("중식", "집밥"),
        ("중식", "한그릇(한정판매)"),
        ("석식", "집밥"),
    ]
    assert third.meals[0].menu.startswith("김치가츠나베(뚝)\n(돼지:국내산)")
    assert "￦7,000" in third.meals[0].menu
    assert [(m.meal, m.corner) for m in second.meals] == [
        ("중식", "일품코너"),
        ("중식", "양식코너"),
        ("중식", "뚝배기코너"),
    ]
    assert [(m.meal, m.corner) for m in first.meals] == [("중·석식", "메뉴"), ("중·석식", None)]
    assert first.meals[0].menu.startswith("****솥밥****")
    assert first.meals[1].menu.startswith("****누들****")
    assert not any(c.closed for c in menu.cafeterias)


def test_parse_closed_day(html_22: str) -> None:
    menu = parse_day_page(html_22, dt.date(2026, 11, 22))

    assert len(menu.cafeterias) == 3
    assert all(c.closed and c.meals == [] for c in menu.cafeterias)


def test_header_date_mismatch_raises(html_19: str) -> None:
    with pytest.raises(PageFormatError):
        parse_day_page(html_19, dt.date(2026, 11, 20))


def test_page_without_tables_raises() -> None:
    with pytest.raises(PageFormatError):
        parse_day_page("<html><body></body></html>", dt.date(2026, 11, 19))


@pytest.mark.anyio
async def test_fetch_decodes_cp949(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=fixture_bytes("cafeteria_2026-11-19.html"))

    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(handler))

    html = await fetch_day_page(dt.date(2026, 11, 19))

    assert "상록원3층식당" in html
    assert requested == [day_url(dt.date(2026, 11, 19))]


@pytest.mark.anyio
async def test_fetch_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    monkeypatch.setattr(source, "HTTP_TRANSPORT", transport)

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_day_page(dt.date(2026, 11, 19))


@pytest.mark.anyio
async def test_fetch_gives_up_after_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await anyio.sleep(1)
        return httpx.Response(200, content=fixture_bytes("cafeteria_2026-11-19.html"))

    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(slow))
    monkeypatch.setattr(source, "FETCH_DEADLINE_SECONDS", 0.05)

    with pytest.raises(TimeoutError):
        await fetch_day_page(dt.date(2026, 11, 19))
