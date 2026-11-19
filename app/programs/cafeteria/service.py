import datetime as dt
import logging
from typing import Any

import httpx

from app.programs.cafeteria import source
from app.programs.cafeteria.schemas import Cafeteria, GetMenuInput
from app.programs.schemas import Candidate, ToolError, ToolNeedClarification, ToolOk

logger = logging.getLogger(__name__)

# 생협 매장 안내의 정식 이름(교직원식당, 상록원학생식당)과 흔히 부르는 이름
ALIASES: dict[str, tuple[str, ...]] = {
    "상록원3층식당": ("3층", "교직원"),
    "상록원2층식당": ("2층", "학생식당"),
    "상록원1층식당(솥앤누들)": ("1층", "솥앤누들", "솥밥", "누들"),
}
ALL_CLOSED_NOTE = "이 날은 모든 식당이 휴무이거나 아직 식단이 올라오지 않았습니다."


def today_kst() -> dt.date:
    return dt.datetime.now(source.KST).date()


def _normalize(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace() and ch not in "()")


def match_cafeterias(query: str, names: list[str]) -> list[str]:
    q = _normalize(query)
    return [
        name
        for name in names
        if q in _normalize(name) or any(alias in q for alias in ALIASES.get(name, ()))
    ]


async def get_menu(args: GetMenuInput, today: dt.date) -> ToolOk | ToolNeedClarification:
    day = args.date or today
    try:
        loaded = await source.load_day_menu(day)
    except (httpx.HTTPError, TimeoutError) as exc:
        raise ToolError("SOURCE_UNAVAILABLE", "학식 사이트에 접속하지 못했습니다.") from exc
    except source.PageFormatError as exc:
        logger.warning("학식 페이지 형식이 예상과 다릅니다: %s", exc)
        raise ToolError(
            "SOURCE_CHANGED", "학식 사이트 형식이 바뀌어 메뉴를 읽지 못했습니다."
        ) from exc

    cafeterias = loaded.value.cafeterias
    if args.cafeteria:
        names = [c.name for c in cafeterias]
        matched = match_cafeterias(args.cafeteria, names)
        if len(matched) != 1:
            return ToolNeedClarification(
                field="cafeteria",
                message="어느 식당인지 골라 주세요.",
                candidates=[Candidate(value=n, label=n) for n in (matched or names)],
            )
        cafeterias = [c for c in cafeterias if c.name == matched[0]]

    llm = _llm(day, today, loaded.stale, cafeterias)
    return ToolOk(llm=llm, ui={**llm, "url": source.day_url(day)})


def _llm(day: dt.date, today: dt.date, stale: bool, cafeterias: list[Cafeteria]) -> dict[str, Any]:
    all_closed = all(c.closed for c in cafeterias)
    return {
        "date": day.isoformat(),
        "today": today.isoformat(),
        "stale": stale,
        "note": ALL_CLOSED_NOTE if all_closed else None,
        "cafeterias": [c.model_dump(mode="json", by_alias=True) for c in cafeterias],
    }
