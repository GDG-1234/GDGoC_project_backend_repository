"""동국대 생협 날짜별 식단 페이지를 읽고 파싱한다.

주소: https://dgucoop.dongguk.edu/store/store.php?w=4&l=1&sday=<그날 0시(한국 시간)의 유닉스 시각>
- 인코딩 EUC-KR(cp949).
- 식당 이름은 `td.menu_st`, 바로 다음 `<table>`이 메뉴 표다.
- 주석(`<!-- -->`) 안에 숨은 식당이 많다. BeautifulSoup은 주석 안 태그를 보지 않는다.
"""

import asyncio
import datetime as dt
import re

import httpx
from bs4 import BeautifulSoup, Tag

from app.common.cache import CacheResult, TtlCache
from app.programs.cafeteria.schemas import Cafeteria, DayMenu, MealMenu

# 한국은 서머타임이 없어 고정 +9시간이면 된다 (ZoneInfo는 Windows에 tzdata가 없으면 실패)
KST = dt.timezone(dt.timedelta(hours=9), "KST")
BASE_URL = "https://dgucoop.dongguk.edu/store/store.php"
USER_AGENT = "Mozilla/5.0 (compatible; gdg1234-bot)"
TIMEOUT_SECONDS = 5  # httpx 단계별(연결·읽기 등) 제한
# 요청 하나 전체 제한. tool 제한(10초)보다 짧아야 실패가 오래된 캐시로 이어진다
FETCH_DEADLINE_SECONDS = 7
FRESH_SECONDS = 600

# 테스트에서 httpx.MockTransport로 바꿔 끼운다
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

HEADER_DATE = re.compile(r"(\d+)월\s*(\d+)일")
DUPLICATED_NAME = re.compile(r"^'(.+)'\1$")  # 첫 줄의 '이름'이름 찌꺼기
CLOSED = "휴무"


class PageFormatError(Exception):
    """페이지는 받았지만 예상한 구조가 아니다 (사이트 구조 변경 의심)."""


def day_url(day: dt.date) -> str:
    sday = int(dt.datetime.combine(day, dt.time(), tzinfo=KST).timestamp())
    return f"{BASE_URL}?w=4&l=1&sday={sday}"


def parse_day_page(html: str, day: dt.date) -> DayMenu:
    soup = BeautifulSoup(html, "html.parser")

    header = soup.select_one("span.menu_date")
    match = HEADER_DATE.search(header.get_text()) if header else None
    if match is None or (int(match[1]), int(match[2])) != (day.month, day.day):
        raise PageFormatError(f"페이지 머리 날짜가 {day}와 다릅니다.")

    names = soup.select("td.menu_st")
    if not names:
        raise PageFormatError("식당 표를 찾지 못했습니다.")

    cafeterias = []
    for name_cell in names:
        name = name_cell.get_text(strip=True)
        if "일산" in name:
            continue
        parent = name_cell.find_parent("table")
        table = parent.find_next("table") if parent else None
        if not isinstance(table, Tag):
            raise PageFormatError(f"{name}의 메뉴 표를 찾지 못했습니다.")
        meals = _parse_menu_table(table)
        cafeterias.append(Cafeteria(name=name, closed=not meals, meals=meals))
    return DayMenu(date=day, cafeterias=cafeterias)


def _parse_menu_table(table: Tag) -> list[MealMenu]:
    rows = table.find_all("tr", recursive=False)
    if not rows:
        return []
    header = [cell.get_text(strip=True) for cell in rows[0].find_all("td", recursive=False)]
    meals = []
    for row in rows[1:]:
        cells = row.find_all("td", recursive=False)
        if not cells:
            continue
        meal = cells[0].get_text(strip=True)
        for index, cell in enumerate(cells[1:], start=1):
            text = _cell_text(cell)
            if not text or text == CLOSED:
                continue
            corner = header[index] if index < len(header) else None
            meals.append(MealMenu(meal=meal, corner=corner, menu=text))
    return meals


def _cell_text(cell: Tag) -> str:
    lines = cell.get_text("\n", strip=True).splitlines()
    if lines:
        lines[0] = DUPLICATED_NAME.sub(r"\1", lines[0])
    return "\n".join(line for line in lines if line)


async def fetch_day_page(day: dt.date) -> str:
    async with httpx.AsyncClient(
        transport=HTTP_TRANSPORT,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        async with asyncio.timeout(FETCH_DEADLINE_SECONDS):
            response = await client.get(day_url(day))
        response.raise_for_status()
        return response.content.decode("cp949", errors="replace")


day_menu_cache: TtlCache[DayMenu] = TtlCache(fresh_seconds=FRESH_SECONDS)


async def _load(day: dt.date) -> DayMenu:
    return parse_day_page(await fetch_day_page(day), day)


async def load_day_menu(day: dt.date) -> CacheResult[DayMenu]:
    return await day_menu_cache.get_or_load(day.isoformat(), lambda: _load(day))
