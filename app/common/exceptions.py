import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """공용 예외. 응답은 `{"error": {"code", "message"}}` 형식이다 (API 명세서 1.5)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class UnauthorizedException(AppException):
    def __init__(self, message: str = "로그인이 필요합니다.") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", message)


class ForbiddenException(AppException):
    def __init__(self, message: str = "권한이 없습니다.") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "FORBIDDEN", message)


class NotFoundException(AppException):
    def __init__(self, code: str = "NOT_FOUND", message: str = "찾을 수 없습니다.") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, code, message)


class EmailNotAllowedException(AppException):
    def __init__(self, email: str) -> None:
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            "EMAIL_NOT_ALLOWED",
            f"허용되지 않은 이메일 도메인입니다. ({email})",
        )


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", str(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("처리하지 못한 오류", exc_info=exc)
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "서버 오류가 발생했습니다."
        )
