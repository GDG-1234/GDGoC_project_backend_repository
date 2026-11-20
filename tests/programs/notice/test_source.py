import datetime as dt
from urllib.parse import quote

import httpx
import pytest

from app.programs.notice import source
from app.programs.notice.schemas import Attachment, NoticeBoard
from app.programs.notice.source import (
    NoticeNotFoundError,
    PageFormatError,
    fetch_detail_page,
    fetch_list_page,
    list_url,
    parse_detail,
    parse_list,
)
from tests.programs.notice.conftest import detail_page


def test_list_url() -> None:
    assert (
        list_url(NoticeBoard.general, None)
        == "https://www.dongguk.edu/article/GENERALNOTICES/list?pageIndex=1"
    )
    assert list_url(NoticeBoard.scholarship, "국가") == (
        "https://www.dongguk.edu/article/JANGHAKNOTICE/list?pageIndex=1"
        "&searchCondition=TA.SUBJECT&searchKeyword=%EA%B5%AD%EA%B0%80"
    )  # 제목만 검색한다. 제목+내용 검색은 학교 서버에서 3~6초가 걸려 시간 제한에 걸린다


def test_list_url_encodes_keyword() -> None:
    assert "searchKeyword=%EA%B5%AD%EA%B0%80+%26+a" in list_url(NoticeBoard.general, "국가 & a")


def test_parse_general_list(general_list_html: str) -> None:
    lst = parse_list(general_list_html, NoticeBoard.general)

    assert [i.article_id for i in lst.pinned] == [
        26767048,
        26767047,
        26767044,
        26767036,
        26767030,
        26767012,
    ]
    assert all(i.pinned for i in lst.pinned)
    assert not any(i.pinned for i in lst.regular)
    assert len(lst.regular) == 10
    assert lst.regular[-1].article_id == 26767004
    first = lst.regular[0]
    assert (
        first.title == "[동국대학교 인권센터] 2026학년도 인권실태조사 참여 안내 (2026.11.17~11.24)"
    )
    assert first.date == dt.date(2026, 11, 19)
    assert first.views == 291
    assert first.board == NoticeBoard.general
    assert first.url == "https://www.dongguk.edu/article/GENERALNOTICES/detail/26767048"


def test_parse_search_list(search_html: str) -> None:
    lst = parse_list(search_html, NoticeBoard.scholarship)

    assert len(lst.pinned) == 10
    assert len(lst.regular) == 10
    assert lst.regular[0].article_id == 26767028


def test_parse_list_without_board_raises() -> None:
    with pytest.raises(PageFormatError):
        parse_list("<html></html>", NoticeBoard.general)


def test_parse_detail_with_attachments(scholarship_detail_html: str) -> None:
    d = parse_detail(scholarship_detail_html, NoticeBoard.scholarship, 26767024)

    assert d.title.startswith("2026학년도 국가우수장학금(이공계)")
    assert d.date == dt.date(2026, 11, 18)
    assert d.views == 879
    assert d.truncated is False
    assert d.body_is_image is False
    first_line = d.body.splitlines()[0]
    assert "자연과학" in first_line and "공학계열" in first_line  # 인라인 태그를 한 줄로 잇는다
    name = "2026-2학기 국가우수(이공계)장학 일시지원유형 신청서.hwp"
    assert d.attachments[0] == Attachment(
        name=name,
        url="https://www.dongguk.edu/cmmn/fileDown.do?filename="
        + quote(name, safe="")
        + "&filepath=/files/article/JANGHAKNOTICE/26767024/"
        + "&filerealname=91093BC65F6B4100A6C9CFE56B08FC3F.hwp",
    )
    assert len(d.attachments) == 2
    assert d.url == "https://www.dongguk.edu/article/JANGHAKNOTICE/detail/26767024"


def test_parse_detail_without_attachments(general_detail_html: str) -> None:
    d = parse_detail(general_detail_html, NoticeBoard.general, 26767048)

    assert d.attachments == []  # 꼬리말 pdf 링크는 첨부가 아니다
    assert d.body.splitlines()[0] == "[동국대학교 인권센터] 2026학년도 인권실태조사 참여 안내"
    assert "https://forms.gle/1Hmey68SP2vxuStQA" in d.body
    assert "$(document)" not in d.body  # script 제거
    assert d.views == 292


def test_parse_detail_truncates() -> None:
    d = parse_detail(detail_page("<p>" + "가" * 5000 + "</p>"), NoticeBoard.general, 1)

    assert len(d.body) == 4000
    assert d.truncated is True


def test_parse_detail_image_only() -> None:
    d = parse_detail(detail_page('<p><img src="/a.png"></p>'), NoticeBoard.general, 1)

    assert d.body_is_image is True


def test_parse_detail_table_cells_on_one_line() -> None:
    html = detail_page("<table><tr><td>구분</td><td>기간</td></tr></table>")

    d = parse_detail(html, NoticeBoard.general, 1)

    assert d.body == "구분 | 기간"


def test_parse_detail_without_view_cont_raises() -> None:
    with pytest.raises(PageFormatError):
        parse_detail("<html></html>", NoticeBoard.general, 1)


@pytest.mark.anyio
async def test_fetch_detail_redirect_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "/main"})
    )
    monkeypatch.setattr(source, "HTTP_TRANSPORT", transport)

    with pytest.raises(NoticeNotFoundError):
        await fetch_detail_page(NoticeBoard.academic, 26767048)


@pytest.mark.anyio
async def test_fetch_list_requests_list_url(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text="<html>목록</html>")

    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(handler))

    html = await fetch_list_page(NoticeBoard.scholarship, "국가")

    assert html == "<html>목록</html>"
    assert requested == [list_url(NoticeBoard.scholarship, "국가")]
