from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_say_hello() -> None:
    response = client.get("/hello/gdgoc")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello gdgoc"}


def test_say_hello_korean_name() -> None:
    response = client.get("/hello/철수")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello 철수"}


def test_unknown_path_returns_404() -> None:
    response = client.get("/not-exists")

    assert response.status_code == 404
