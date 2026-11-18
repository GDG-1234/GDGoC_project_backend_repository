from fastapi import APIRouter, status

from app.auth import service
from app.auth.dependencies import AdminUser, CurrentUser, SessionDep, SettingsDep
from app.auth.schemas import UserResponse
from app.common.schemas import ItemsResponse

router = APIRouter(prefix="/api/v1")


@router.get(
    "/users/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    tags=["users"],
    summary="내 정보 (처음 호출하면 회원가입)",
)
async def read_me(user: CurrentUser, settings: SettingsDep) -> UserResponse:
    return service.to_response(user, settings)


@router.get(
    "/admin/users",
    response_model=ItemsResponse[UserResponse],
    status_code=status.HTTP_200_OK,
    tags=["admin"],
    summary="전체 사용자 목록 (관리자 전용)",
)
async def list_users(
    _: AdminUser, session: SessionDep, settings: SettingsDep
) -> ItemsResponse[UserResponse]:
    users = await service.list_users(session)
    return ItemsResponse(items=[service.to_response(user, settings) for user in users])
