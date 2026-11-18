from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse


class AppError(Exception):
    """앱 전체에서 쓰는 기본 예외"""
    def __init__(
        self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

class UnauthorizedError(AppError):
    def __init__(self, message: str = "인증이 필요합니다.") -> None:
        super().__init__("UNAUTHORIZED", message, status.HTTP_401_UNAUTHORIZED)

class NotFoundError(AppError):
    def __init__(self, code: str = "NOT_FOUND", message: str = "찾을 수 없습니다.") -> None:
        super().__init__(code, message, status.HTTP_404_NOT_FOUND)

def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}

async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content=error_body(
            "VALIDATION_ERROR", "요청 형식이 올바르지 않습니다.", jsonable_encoder(exc.errors())
        ),
    )

def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
