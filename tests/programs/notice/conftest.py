from pathlib import Path

import anyio
import httpx
import pytest

from app.common.cache import TtlCache
from app.programs.notice import source

FIXTURES = Path(__file__).parent / "fixtures"
EMPTY_LIST = '<div class="board_list"><ul></ul></div>'


class FakeDongguk:
    """동국대 홈페이지 흉내. 저장해 둔 목록·본문을 주소에 맞춰 돌려준다."""

    def __init__(self) -> None:
        self.lists = {
            ("GENERALNOTICES", None): fixture_text("notice_general_list.html"),
            ("JANGHAKNOTICE", "국가"): fixture_text("notice_scholarship_search.html"),
        }
        self.details = {
            ("GENERALNOTICES", "26767048"): fixture_text("notice_general_26767048.html"),
            ("JANGHAKNOTICE", "26767024"): fixture_text("notice_scholarship_26767024.html"),
        }
        self.down: set[str] = set()  # 접속이 안 되는 게시판 코드
        self.slow: set[str] = set()  # 응답이 느린 게시판 코드 (async_handler에서만)

    def handler(self, request: httpx.Request) -> httpx.Response:
        _, _, code, kind, *rest = request.url.path.split("/")
        if code in self.down:
            raise httpx.ConnectTimeout("timed out", request=request)
        if kind == "list":
            keyword = request.url.params.get("searchKeyword")
            return httpx.Response(200, text=self.lists.get((code, keyword), EMPTY_LIST))
        page = self.details.get((code, rest[0]))
        if page is None:
            return httpx.Response(302, headers={"Location": "/main"})
        return httpx.Response(200, text=page)

    async def async_handler(self, request: httpx.Request) -> httpx.Response:
        """`slow`에 든 게시판은 응답이 1초 걸린다 (전체 시간 제한 테스트용)."""
        if request.url.path.split("/")[2] in self.slow:
            await anyio.sleep(1)
        return self.handler(request)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeDongguk:
    """학교 사이트 대신 FakeDongguk을 쓰고, 테스트마다 빈 캐시로 시작한다."""
    fake = FakeDongguk()
    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(source, "list_cache", TtlCache(fresh_seconds=source.LIST_FRESH_SECONDS))
    monkeypatch.setattr(source, "detail_cache", TtlCache(fresh_seconds=source.DETAIL_FRESH_SECONDS))
    return fake


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def general_list_html() -> str:
    """일반공지 목록 1쪽 (2026-11-19). 고정 6개 + 일반 10개."""
    return fixture_text("notice_general_list.html")


@pytest.fixture
def search_html() -> str:
    """장학공지 "국가" 검색 1쪽. 고정 10개(검색어와 무관) + 일반 10개."""
    return fixture_text("notice_scholarship_search.html")


@pytest.fixture
def scholarship_detail_html() -> str:
    """장학공지 26767024 본문. 첨부파일 2개."""
    return fixture_text("notice_scholarship_26767024.html")


@pytest.fixture
def general_detail_html() -> str:
    """일반공지 26767048 본문. 첨부파일 없음."""
    return fixture_text("notice_general_26767048.html")


def detail_page(view_cont: str) -> str:
    """본문만 바꾼 최소 본문 페이지."""
    return (
        '<div class="board_view"><div class="tit"><p>제목</p><div class="info">'
        "<span>등록일 2026.11.18.</span><span>조회 10</span></div></div>"
        f'<div class="view_cont">{view_cont}</div></div>'
    )
