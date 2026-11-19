import asyncio
import logging

import httpx

from app.common.cache import CacheResult
from app.programs.notice import source
from app.programs.notice.schemas import (
    DetailInput,
    NoticeBoard,
    NoticeItem,
    NoticeList,
    SearchInput,
)
from app.programs.schemas import ToolError, ToolOk

logger = logging.getLogger(__name__)

DEFAULT_BOARDS = (NoticeBoard.general, NoticeBoard.academic, NoticeBoard.scholarship)
SOURCE_ERRORS = (httpx.HTTPError, TimeoutError, source.PageFormatError)
UNAVAILABLE_ERRORS = (httpx.HTTPError, TimeoutError)


def merge_items(lists: list[NoticeList], with_pinned: bool, limit: int) -> list[NoticeItem]:
    merged: dict[tuple[NoticeBoard, int], NoticeItem] = {}
    for notice_list in lists:
        items = notice_list.pinned + notice_list.regular if with_pinned else notice_list.regular
        for item in items:
            key = (item.board, item.article_id)
            if key not in merged or (item.pinned and not merged[key].pinned):
                merged[key] = item
    ordered = sorted(merged.values(), key=lambda i: (i.date, i.article_id), reverse=True)
    return ordered[:limit]


def _source_error(errors: list[BaseException]) -> ToolError:
    if any(isinstance(e, UNAVAILABLE_ERRORS) for e in errors):
        return ToolError("SOURCE_UNAVAILABLE", "학교 홈페이지에 접속하지 못했습니다.")
    logger.warning("공지 페이지 형식이 예상과 다릅니다: %s", errors)
    return ToolError("SOURCE_CHANGED", "학교 홈페이지 형식이 바뀌어 공지를 읽지 못했습니다.")


async def search(args: SearchInput) -> ToolOk:
    boards = [args.board] if args.board else list(DEFAULT_BOARDS)
    results = await asyncio.gather(
        *(source.load_list(board, args.keyword) for board in boards), return_exceptions=True
    )

    loaded: list[CacheResult[NoticeList]] = []
    failed: list[NoticeBoard] = []
    errors: list[BaseException] = []
    for board, result in zip(boards, results, strict=True):
        if isinstance(result, SOURCE_ERRORS):
            failed.append(board)
            errors.append(result)
        elif isinstance(result, BaseException):
            raise result
        else:
            loaded.append(result)
    if not loaded:
        raise _source_error(errors)

    # 검색할 때 고정 공지는 검색어와 상관없이 전부 나오므로 버린다
    items = merge_items(
        [r.value for r in loaded], with_pinned=args.keyword is None, limit=args.limit
    )
    dumped = [i.model_dump(mode="json", by_alias=True) for i in items]
    llm = {
        "board": args.board,
        "keyword": args.keyword,
        "stale": any(r.stale for r in loaded),
        "failedBoards": [str(b) for b in failed],
        "items": dumped,
    }
    return ToolOk(llm=llm, ui={"items": dumped})


async def get_detail(args: DetailInput) -> ToolOk:
    try:
        loaded = await source.load_detail(args.board, args.article_id)
    except source.NoticeNotFoundError as exc:
        raise ToolError(
            "NOTICE_NOT_FOUND", "해당 공지를 찾지 못했습니다. 게시판과 글번호를 확인하세요."
        ) from exc
    except SOURCE_ERRORS as exc:
        raise _source_error([exc]) from exc

    detail = loaded.value
    llm = {**detail.model_dump(mode="json", by_alias=True), "stale": loaded.stale}
    ui = {
        "title": detail.title,
        "date": detail.date.isoformat(),
        "url": detail.url,
        "attachments": llm["attachments"],
    }
    return ToolOk(llm=llm, ui=ui)
