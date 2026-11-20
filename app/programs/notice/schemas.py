import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field

from app.common.schemas import CamelModel


class NoticeBoard(StrEnum):
    general = "general"
    academic = "academic"
    scholarship = "scholarship"
    admission = "admission"
    research = "research"
    event = "event"
    international = "international"
    foreign_student = "foreign_student"
    safety = "safety"


# 동국대 홈페이지 게시판 코드 (https://www.dongguk.edu/article/<코드>/list)
BOARD_CODES: dict[NoticeBoard, str] = {
    NoticeBoard.general: "GENERALNOTICES",  # 일반공지
    NoticeBoard.academic: "HAKSANOTICE",  # 학사공지
    NoticeBoard.scholarship: "JANGHAKNOTICE",  # 장학공지
    NoticeBoard.admission: "IPSINOTICE",  # 입시공지
    NoticeBoard.research: "HAKSULNOTICE",  # 학술공지
    NoticeBoard.event: "BUDDHISTEVENT",  # 행사공지(정각원 법회 등 불교 행사)
    NoticeBoard.international: "INTEXNOTICE",  # 국제교류(교환학생 등)
    NoticeBoard.foreign_student: "INTSTUNOTICE",  # 외국인 유학생
    NoticeBoard.safety: "SAFENOTICE",  # 안전공지
}

BOARD_DESCRIPTION = (
    "게시판. general=일반, academic=학사, scholarship=장학, admission=입시, research=학술, "
    "event=불교 행사(법회), international=국제교류·교환학생, foreign_student=외국인 유학생, "
    "safety=안전"
)

# ---- tool 입력 (LLM이 보는 JSON Schema라 BaseModel을 쓴다) ----


class SearchInput(BaseModel):
    board: NoticeBoard | None = Field(
        None, description=BOARD_DESCRIPTION + ". 없으면 일반·학사·장학 공지를 함께 본다"
    )
    keyword: str | None = Field(None, min_length=1, max_length=50, description="제목 검색어")
    limit: int = Field(5, ge=1, le=10, description="가져올 개수")


class DetailInput(BaseModel):
    board: NoticeBoard = Field(description="notice_search 결과의 board")
    article_id: int = Field(gt=0, description="notice_search 결과의 articleId")


# ---- 홈페이지에서 읽은 데이터 ----


class NoticeItem(CamelModel):
    board: NoticeBoard
    article_id: int
    title: str
    date: dt.date
    views: int
    pinned: bool
    url: str


class NoticeList(CamelModel):
    pinned: list[NoticeItem]  # 고정 공지 (검색어와 상관없이 전부 나온다)
    regular: list[NoticeItem]


class Attachment(CamelModel):
    name: str
    url: str


class NoticeDetail(CamelModel):
    board: NoticeBoard
    article_id: int
    title: str
    date: dt.date
    views: int
    body: str
    truncated: bool
    body_is_image: bool
    attachments: list[Attachment]
    url: str
