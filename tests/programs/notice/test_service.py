import httpx
import pytest

from app.programs.notice import source
from app.programs.notice.schemas import DetailInput, NoticeBoard, SearchInput
from app.programs.notice.service import get_detail, merge_items, search
from app.programs.notice.source import parse_list
from app.programs.schemas import ToolError
from tests.programs.notice.conftest import FakeDongguk


def test_merge_with_pinned(general_list_html: str) -> None:
    items = merge_items(
        [parse_list(general_list_html, NoticeBoard.general)], with_pinned=True, limit=5
    )

    assert [i.article_id for i in items] == [26767048, 26767047, 26767044, 26767036, 26767030]
    assert all(i.pinned for i in items)  # 일반 목록의 중복은 고정 표시를 유지한 채 하나로


def test_merge_search_drops_pinned_list(search_html: str) -> None:
    items = merge_items(
        [parse_list(search_html, NoticeBoard.scholarship)], with_pinned=False, limit=3
    )

    assert [i.article_id for i in items] == [26767028, 26767024, 26766019]
    assert not any(i.pinned for i in items)


pytestmark = pytest.mark.anyio


async def test_search_one_board(site: FakeDongguk) -> None:
    result = await search(SearchInput(board=NoticeBoard.general, limit=3))

    assert result.llm["board"] == "general"
    assert result.llm["keyword"] is None
    assert result.llm["failedBoards"] == []
    assert result.llm["stale"] is False
    assert [i["articleId"] for i in result.llm["items"]] == [26767048, 26767047, 26767044]
    assert result.ui == {"items": result.llm["items"]}


async def test_search_default_boards_partial_failure(site: FakeDongguk) -> None:
    site.down = {"HAKSANOTICE", "JANGHAKNOTICE"}

    result = await search(SearchInput())

    assert result.llm["board"] is None
    assert result.llm["failedBoards"] == ["academic", "scholarship"]
    assert {i["board"] for i in result.llm["items"]} == {"general"}
    assert len(result.llm["items"]) == 5


async def test_search_all_fail(site: FakeDongguk) -> None:
    site.down = {"GENERALNOTICES", "HAKSANOTICE", "JANGHAKNOTICE"}

    with pytest.raises(ToolError) as error:
        await search(SearchInput())

    assert error.value.code == "SOURCE_UNAVAILABLE"


async def test_search_no_results(site: FakeDongguk) -> None:
    result = await search(SearchInput(board=NoticeBoard.safety, keyword="없는검색어"))

    assert result.llm["items"] == []


async def test_get_detail(site: FakeDongguk) -> None:
    result = await get_detail(DetailInput(board=NoticeBoard.scholarship, article_id=26767024))

    assert result.llm["articleId"] == 26767024
    assert result.llm["bodyIsImage"] is False
    assert len(result.llm["attachments"]) == 2
    assert result.llm["stale"] is False
    assert result.ui is not None
    assert "body" not in result.ui
    assert result.ui["url"].endswith("/JANGHAKNOTICE/detail/26767024")


async def test_get_detail_not_found(site: FakeDongguk) -> None:
    with pytest.raises(ToolError) as error:
        await get_detail(DetailInput(board=NoticeBoard.academic, article_id=26767024))

    assert error.value.code == "NOTICE_NOT_FOUND"


async def test_search_slow_board_is_reported_failed(
    site: FakeDongguk, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source, "FETCH_DEADLINE_SECONDS", 0.05)
    site.slow = {"HAKSANOTICE"}
    monkeypatch.setattr(source, "HTTP_TRANSPORT", httpx.MockTransport(site.async_handler))

    result = await search(SearchInput())

    assert result.llm["failedBoards"] == ["academic"]
    assert result.llm["items"] != []
