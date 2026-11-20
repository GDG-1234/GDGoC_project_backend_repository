import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from app.common.exceptions import NotFoundException
from app.programs.registry import ToolRegistry
from app.programs.result_store import ResultStore, StoredResult
from app.programs.schemas import (
    ErrorInfo,
    InvokeErrorResponse,
    InvokeNeedClarificationResponse,
    InvokeOkResponse,
    InvokeResponse,
    ToolError,
    ToolInfo,
    ToolNeedClarification,
    ToolOk,
)

logger = logging.getLogger(__name__)


def list_tools(registry: ToolRegistry) -> list[ToolInfo]:
    return [
        ToolInfo(name=t.name, description=t.description, input_schema=t.input_schema())
        for t in registry.all()
    ]


def _error(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> InvokeErrorResponse:
    return InvokeErrorResponse(error=ErrorInfo(code=code, message=message, details=details))


async def invoke_tool(
    registry: ToolRegistry,
    store: ResultStore,
    name: str,
    arguments: dict[str, Any],
    default_timeout: float,
) -> InvokeResponse:
    registered = registry.get(name)
    if registered is None:
        raise NotFoundException("TOOL_NOT_FOUND", f"'{name}' tool이 없습니다.")

    try:
        args = registered.input_model.model_validate(arguments)
    except ValidationError as exc:
        details = exc.errors(include_url=False, include_context=False)
        return _error("INVALID_ARGUMENTS", "입력값이 올바르지 않습니다.", list(details))

    timeout = registered.timeout if registered.timeout is not None else default_timeout
    try:
        result = await asyncio.wait_for(registered.func(args), timeout=timeout)
    except TimeoutError:
        return _error("TOOL_TIMEOUT", f"{timeout}초 안에 끝나지 않았습니다.")
    except ToolError as exc:
        return _error(exc.code, exc.message, exc.details)
    except Exception:
        logger.exception("tool 실행 실패: %s", name)
        return _error("TOOL_FAILED", "tool 실행 중 오류가 났습니다.")

    if isinstance(result, ToolNeedClarification):
        return InvokeNeedClarificationResponse(
            field=result.field, message=result.message, candidates=result.candidates
        )
    if not isinstance(result, ToolOk):
        logger.error("tool이 ToolOk/ToolNeedClarification이 아닌 값을 반환했습니다: %s", name)
        return _error("TOOL_FAILED", "tool 실행 중 오류가 났습니다.")

    result_id = await store.put(name, result.ui) if result.ui is not None else None
    return InvokeOkResponse(llm=result.llm, result_id=result_id)


async def get_ui_result(store: ResultStore, result_id: str) -> StoredResult | None:
    """채팅 창구가 result_id로 ui를 꺼낼 때 쓴다."""
    return await store.get(result_id)
