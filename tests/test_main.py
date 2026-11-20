from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_unknown_path_returns_404() -> None:
    response = client.get("/not-exists")

    assert response.status_code == 404
