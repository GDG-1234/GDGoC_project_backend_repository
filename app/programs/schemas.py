from typing import Any, Literal, Annotated

from pydantic import BaseModel, Field


class ToolOk(BaseModel):
    """tool 성공 결과. llm은 AI에게 주고, ui는 백엔드가 보관한다."""

    llm: dict[str, Any]
    ui: dict[str, Any] | None = None

class Candidate(BaseModel):
    value: str
    label: str
    description: str | None = None

class ToolNeedClarification(BaseModel):
    # 입력이 애매할 때, 후보만 주고, 되묻는 문장은 AI가 쓴다

    field: str
    message: str
    candidates: list[Candidate]

ToolResult = ToolOk | ToolNeedClarification

class ToolError(Exception):
    # tool 안에서 예상된 실패를 알릴 때 던진다. 예: 메뉴 없음.

    def __init__(self, code: str, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

# API 요청 응답

class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]

class ToolListResponse(BaseModel):
    tools: list[ToolInfo]

class InvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)

class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None

class InvokeOkResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm: dict[str, Any]
    result_id: str | None

class InvokeNeedClarificationResponse(BaseModel):
    status: Literal["need_clarification"] = "need_clarification"
    field: str
    message: str
    candidates: list[Candidate]

class InvokeErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorInfo

InvokeNeedClarificationResponse = Annotated[
    InvokeOkResponse | InvokeNeedClarificationResponse | InvokeErrorResponse,
    Field(discriminator="status"),
]
