"""동국대 홈페이지 공지 목록·본문을 읽고 파싱한다.

- 목록: /article/<게시판코드>/list?pageIndex=1[&searchCondition=...&searchKeyword=...]
- 본문: /article/<게시판코드>/detail/<글번호>. 게시판이 틀리거나 없는 글이면 302로 /main에 보낸다.
"""

import asyncio
import datetime as dt
import re
from urllib.parse import quote, urlencode

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from app.common.cache import CacheResult, TtlCache
from app.programs.notice.schemas import (
    BOARD_CODES,
    Attachment,
    NoticeBoard,
    NoticeDetail,
    NoticeItem,
    NoticeList,
)

BASE_URL = "https://www.dongguk.edu"
USER_AGENT = "Mozilla/5.0 (compatible; gdg1234-bot)"
TIMEOUT_SECONDS = 5  # httpx 단계별(연결·읽기 등) 제한
# 요청 하나 전체 제한. tool 제한(10초)보다 짧아야 실패가 오래된 캐시로 이어진다
FETCH_DEADLINE_SECONDS = 7
LIST_FRESH_SECONDS = 300
DETAIL_FRESH_SECONDS = 1800
DETAIL_MAX_ITEMS = 300
MAX_BODY_CHARS = 4000
IMAGE_BODY_THRESHOLD = 50
# 제목만 검색한다. 제목+내용(TA.SUBJECT||TA.CONTENT)은 학교 서버에서 3~6초가 걸려 시간 제한에 걸린다
SEARCH_CONDITION = "TA.SUBJECT"

# 테스트에서 httpx.MockTransport로 바꿔 끼운다
HTTP_TRANSPORT: httpx.AsyncBaseTransport | None = None

ARTICLE_ID = re.compile(r"goDetail\((\d+)\)")
DATE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")
NUMBER = re.compile(r"\d[\d,]*")
DOWN_GO = re.compile(r"downGO\('(.*?)','(.*?)','(.*?)'\)")
SPACES = re.compile(r"\s+")
CELL_SEPARATOR = " | "
BLOCK_TAGS = ["p", "div", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"]


class PageFormatError(Exception):
    """페이지는 받았지만 예상한 구조가 아니다 (사이트 구조 변경 의심)."""


class NoticeNotFoundError(Exception):
    """글이 없거나 게시판 코드가 틀렸다."""


def list_url(board: NoticeBoard, keyword: str | None) -> str:
    params = {"pageIndex": "1"}
    if keyword:
        params |= {"searchCondition": SEARCH_CONDITION, "searchKeyword": keyword}
    return f"{BASE_URL}/article/{BOARD_CODES[board]}/list?{urlencode(params)}"


def detail_url(board: NoticeBoard, article_id: int) -> str:
    return f"{BASE_URL}/article/{BOARD_CODES[board]}/detail/{article_id}"


def _parse_date(text: str) -> dt.date:
    match = DATE.search(text)
    if match is None:
        raise PageFormatError(f"날짜를 읽지 못했습니다: {text!r}")
    return dt.date(int(match[1]), int(match[2]), int(match[3]))


def _parse_views(text: str) -> int:
    match = NUMBER.search(text)
    if match is None:
        raise PageFormatError(f"조회수를 읽지 못했습니다: {text!r}")
    return int(match[0].replace(",", ""))


def parse_list(html: str, board: NoticeBoard) -> NoticeList:
    soup = BeautifulSoup(html, "html.parser")
    board_list = soup.select_one("div.board_list")
    if board_list is None:
        raise PageFormatError("공지 목록을 찾지 못했습니다.")

    pinned: list[NoticeItem] = []
    regular: list[NoticeItem] = []
    for li in board_list.select("li"):
        link = li.find("a", onclick=ARTICLE_ID)
        title = li.select_one("p.tit")
        info = li.select("div.info span")
        if not isinstance(link, Tag) or title is None or len(info) < 2:
            continue
        match = ARTICLE_ID.search(str(link["onclick"]))
        if match is None:
            continue
        for mobile in title.select("span.mobile"):
            mobile.decompose()
        is_pinned = li.select_one("span.fix") is not None
        article_id = int(match[1])
        item = NoticeItem(
            board=board,
            article_id=article_id,
            title=title.get_text(strip=True),
            date=_parse_date(info[0].get_text()),
            views=_parse_views(info[1].get_text()),
            pinned=is_pinned,
            url=detail_url(board, article_id),
        )
        (pinned if is_pinned else regular).append(item)
    return NoticeList(pinned=pinned, regular=regular)


def html_to_text(element: Tag) -> str:
    """본문 HTML을 줄 단위 텍스트로 바꾼다.

    `get_text("\\n")`은 인라인 태그(span 등)마다 줄을 끊어서 쓰지 않는다.
    블록 태그 뒤에만 줄바꿈을 넣고, 표 칸은 " | "로 이어 한 줄로 만든다.
    """
    for tag in element.find_all(["script", "style"]):
        tag.decompose()
    for br in element.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for cell in element.find_all(["td", "th"]):
        cell.append(NavigableString(CELL_SEPARATOR))
    for block in element.find_all(BLOCK_TAGS):
        block.append(NavigableString("\n"))

    lines = []
    for raw in element.get_text("").splitlines():
        line = SPACES.sub(" ", raw.replace("\xa0", " ")).strip()
        line = line.removesuffix(CELL_SEPARATOR.strip()).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_detail(html: str, board: NoticeBoard, article_id: int) -> NoticeDetail:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one("div.board_view div.view_cont")
    title = soup.select_one("div.board_view div.tit > p")
    info = soup.select("div.board_view div.tit div.info span")
    if content is None or title is None or len(info) < 2:
        raise PageFormatError("공지 본문을 찾지 못했습니다.")

    body = html_to_text(content)
    attachments = []
    for link in soup.select("div.board_view div.view_files li a"):
        match = DOWN_GO.search(str(link.get("href", "")))
        if match is None:
            continue
        name, path, real_name = match.groups()
        url = (
            f"{BASE_URL}/cmmn/fileDown.do?filename={quote(name, safe='')}"
            f"&filepath={path}&filerealname={real_name}"
        )
        attachments.append(Attachment(name=name, url=url))

    return NoticeDetail(
        board=board,
        article_id=article_id,
        title=title.get_text(strip=True),
        date=_parse_date(info[0].get_text()),
        views=_parse_views(info[1].get_text()),
        body=body[:MAX_BODY_CHARS],
        truncated=len(body) > MAX_BODY_CHARS,
        body_is_image=len(body) < IMAGE_BODY_THRESHOLD,
        attachments=attachments,
        url=detail_url(board, article_id),
    )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=HTTP_TRANSPORT,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    )


async def fetch_list_page(board: NoticeBoard, keyword: str | None) -> str:
    async with _client() as client:
        async with asyncio.timeout(FETCH_DEADLINE_SECONDS):
            response = await client.get(list_url(board, keyword))
        response.raise_for_status()
        return response.text


async def fetch_detail_page(board: NoticeBoard, article_id: int) -> str:
    async with _client() as client:
        async with asyncio.timeout(FETCH_DEADLINE_SECONDS):
            response = await client.get(detail_url(board, article_id))
        if response.is_redirect:
            raise NoticeNotFoundError(f"{board} {article_id}")
        response.raise_for_status()
        return response.text


list_cache: TtlCache[NoticeList] = TtlCache(fresh_seconds=LIST_FRESH_SECONDS)
detail_cache: TtlCache[NoticeDetail] = TtlCache(
    fresh_seconds=DETAIL_FRESH_SECONDS, max_items=DETAIL_MAX_ITEMS
)


async def _load_list(board: NoticeBoard, keyword: str | None) -> NoticeList:
    return parse_list(await fetch_list_page(board, keyword), board)


async def _load_detail(board: NoticeBoard, article_id: int) -> NoticeDetail:
    return parse_detail(await fetch_detail_page(board, article_id), board, article_id)


async def load_list(board: NoticeBoard, keyword: str | None) -> CacheResult[NoticeList]:
    return await list_cache.get_or_load(
        f"{board}|{keyword or ''}", lambda: _load_list(board, keyword)
    )


async def load_detail(board: NoticeBoard, article_id: int) -> CacheResult[NoticeDetail]:
    return await detail_cache.get_or_load(
        f"{board}|{article_id}", lambda: _load_detail(board, article_id)
    )
