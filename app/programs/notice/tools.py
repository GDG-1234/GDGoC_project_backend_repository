from app.programs.notice import service
from app.programs.notice.schemas import DetailInput, SearchInput
from app.programs.registry import tool
from app.programs.schemas import ToolOk


@tool(
    name="notice_search",
    description=(
        "동국대 홈페이지 공지사항 최근 글을 찾는다. "
        "본문이 필요하면 결과의 board, articleId로 notice_get_detail을 부른다."
    ),
)
async def search(args: SearchInput) -> ToolOk:
    return await service.search(args)


@tool(
    name="notice_get_detail",
    description=(
        "동국대 공지사항 글 하나의 본문과 첨부파일 목록을 가져온다. "
        "board와 articleId는 notice_search 결과에서 쓴다."
    ),
)
async def get_detail(args: DetailInput) -> ToolOk:
    return await service.get_detail(args)
