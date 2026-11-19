import datetime as dt

import httpx
import pytest

from app.programs.cafeteria import source
from app.programs.cafeteria.schemas import GetMenuInput
from app.programs.cafeteria.service import ALL_CLOSED_NOTE, get_menu, match_cafeterias
from app.programs.schemas import ToolError, ToolNeedClarification, ToolOk
from tests.programs.cafeteria.conftest import Clock, FakeCoop

NAMES = ["상록원3층식당", "상록원2층식당", "상록원1층식당(솥앤누들)"]
TODAY = dt.date(2026, 11, 19)


def test_match_cafeterias() -> None:
    assert match_cafeterias("3층", NAMES) == ["상록원3층식당"]
    assert match_cafeterias("교직원 식당", NAMES) == ["상록원3층식당"]
    assert match_cafeterias("상록원학생식당", NAMES) == ["상록원2층식당"]
    assert match_cafeterias("솥앤누들", NAMES) == ["상록원1층식당(솥앤누들)"]
    assert match_cafeterias("상록원", NAMES) == NAMES
    assert match_cafeterias("그루터기", NAMES) == []


pytestmark = pytest.mark.anyio


async def test_get_menu_today_all(coop: FakeCoop) -> None:
    result = await get_menu(GetMenuInput(), today=TODAY)

    assert isinstance(result, ToolOk)
    assert result.llm["date"] == "2026-11-19"
    assert result.llm["today"] == "2026-11-19"
    assert result.llm["stale"] is False
    assert result.llm["note"] is None
    assert [c["name"] for c in result.llm["cafeterias"]] == NAMES
    assert result.ui is not None
    assert result.ui["url"].endswith("sday=1795014000")


async def test_get_menu_one_cafeteria(coop: FakeCoop) -> None:
    result = await get_menu(GetMenuInput(cafeteria="3층"), today=TODAY)

    assert isinstance(result, ToolOk)
    assert [c["name"] for c in result.llm["cafeterias"]] == ["상록원3층식당"]


async def test_get_menu_other_date(coop: FakeCoop) -> None:
    result = await get_menu(GetMenuInput(date=dt.date(2026, 11, 22)), today=TODAY)

    assert isinstance(result, ToolOk)
    assert result.llm["date"] == "2026-11-22"
    assert result.llm["today"] == "2026-11-19"
    assert all(c["closed"] for c in result.llm["cafeterias"])
    assert result.llm["note"] == ALL_CLOSED_NOTE


async def test_get_menu_ambiguous(coop: FakeCoop) -> None:
    result = await get_menu(GetMenuInput(cafeteria="상록원"), today=TODAY)

    assert isinstance(result, ToolNeedClarification)
    assert result.field == "cafeteria"
    assert [c.value for c in result.candidates] == NAMES


async def test_get_menu_unknown_cafeteria(coop: FakeCoop) -> None:
    result = await get_menu(GetMenuInput(cafeteria="그루터기"), today=TODAY)

    assert isinstance(result, ToolNeedClarification)
    assert [c.value for c in result.candidates] == NAMES


async def test_get_menu_source_down(coop: FakeCoop) -> None:
    coop.down = True

    with pytest.raises(ToolError) as error:
        await get_menu(GetMenuInput(), today=TODAY)

    assert error.value.code == "SOURCE_UNAVAILABLE"


async def test_get_menu_source_changed(coop: FakeCoop) -> None:
    coop.broken = True

    with pytest.raises(ToolError) as error:
        await get_menu(GetMenuInput(), today=TODAY)

    assert error.value.code == "SOURCE_CHANGED"


async def test_get_menu_stale_when_source_down(coop: FakeCoop, clock: Clock) -> None:
    first = await get_menu(GetMenuInput(), today=TODAY)
    clock.now = 601
    coop.down = True

    result = await get_menu(GetMenuInput(), today=TODAY)

    assert isinstance(first, ToolOk) and isinstance(result, ToolOk)
    assert result.llm["stale"] is True
    assert result.llm["cafeterias"] == first.llm["cafeterias"]


async def test_get_menu_slow_site_is_source_unavailable(
    coop: FakeCoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source, "FETCH_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(coop.slow_handler))

    with pytest.raises(ToolError) as error:
        await get_menu(GetMenuInput(), today=TODAY)

    assert error.value.code == "SOURCE_UNAVAILABLE"
