from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.schemas import ItemsResponse
from app.core.config import Settings, get_settings
from app.programs import service
from app.programs.dependencies import get_registry, get_result_store, verify_service_key
from app.programs.registry import ToolRegistry
from app.programs.result_store import ResultStore
from app.programs.schemas import InvokeRequest, InvokeResponse, ToolInfo

router = APIRouter(prefix="/api/v1/skills", dependencies=[Depends(verify_service_key)])


@router.get(
    "",
    response_model=ItemsResponse[ToolInfo],
    status_code=status.HTTP_200_OK,
    tags=["skills"],
    summary="tool 목록 (AI 서비스 전용)",
)
async def list_skills(
    registry: Annotated[ToolRegistry, Depends(get_registry)],
) -> ItemsResponse[ToolInfo]:
    return ItemsResponse(items=service.list_tools(registry))


@router.post(
    "/{name}/invoke",
    response_model=InvokeResponse,
    status_code=status.HTTP_200_OK,
    tags=["skills"],
    summary="tool 실행 (AI 서비스 전용)",
)
async def invoke_skill(
    name: str,
    body: InvokeRequest,
    registry: Annotated[ToolRegistry, Depends(get_registry)],
    store: Annotated[ResultStore, Depends(get_result_store)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InvokeResponse:
    return await service.invoke_tool(
        registry, store, name, body.arguments, settings.tool_timeout_seconds
    )
