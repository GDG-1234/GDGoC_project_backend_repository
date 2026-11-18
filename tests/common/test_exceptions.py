from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common.exceptions import NotFoundError, UnauthorizedError, register_exception_handlers

app = FastAPI()
register_exception_handlers(app)

@app.get("/not-found")
async def raise_not_found() -> None:
    raise NotFoundError("THING_NOT_FOUND", "없습니다.")

@app.get("/unauthorized")
async def raise_unauthorized() -> None:
    raise UnauthorizedError()

@app.get("/items/{item_id}")
async def get_item(item_id: int) -> dict[str, int]:
    return {"item_id": item_id}

client = TestClient(app)

def test_app_error_uses_common_format() -> None:
    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "THING_NOT_FOUND", "message": "없습니다."}}

def test_unauthorized_error_is_401() -> None:
    response = client.get("/unauthorized")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"

def test_request_validation_error_uses_common_format() -> None:
    response = client.get("/items/not-a-number")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["path", "item_id"]
