import pytest
from httpx import AsyncClient

from app.auth import firebase
from app.common.exceptions import UnauthorizedException
from app.core.config import Settings
from tests.conftest import ADMIN_EMAIL, auth

pytestmark = pytest.mark.anyio


async def test_no_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_first_login_creates_user(client: AsyncClient) -> None:
    first = await client.get("/api/v1/users/me", headers=auth("alice@dgu.ac.kr"))
    second = await client.get("/api/v1/users/me", headers=auth("alice@dgu.ac.kr"))

    assert first.status_code == 200
    body = first.json()
    assert body["email"] == "alice@dgu.ac.kr"
    assert body["name"] == "alice"
    assert body["isAdmin"] is False
    assert {"pictureUrl", "createdAt"} <= body.keys()
    assert second.json()["id"] == body["id"]


async def test_admin_email_is_admin(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me", headers=auth(ADMIN_EMAIL))

    assert response.json()["isAdmin"] is True


async def test_admin_can_list_users(client: AsyncClient) -> None:
    await client.get("/api/v1/users/me", headers=auth("alice@dgu.ac.kr"))

    response = await client.get("/api/v1/admin/users", headers=auth(ADMIN_EMAIL))

    assert response.status_code == 200
    emails = [user["email"] for user in response.json()["items"]]
    assert emails == ["alice@dgu.ac.kr", ADMIN_EMAIL]


async def test_non_admin_cannot_list_users(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/users", headers=auth("alice@dgu.ac.kr"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_email_domain_restriction(client: AsyncClient, settings: Settings) -> None:
    settings.allowed_email_domains = ["dgu.ac.kr"]

    blocked = await client.get("/api/v1/users/me", headers=auth("bob@gmail.com"))
    allowed = await client.get("/api/v1/users/me", headers=auth("alice@dgu.ac.kr"))

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "EMAIL_NOT_ALLOWED"
    assert allowed.status_code == 200


@pytest.fixture
def project_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        firebase, "get_settings", lambda: Settings(firebase_project_id="test-project")
    )


def fake_claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "iss": "https://securetoken.google.com/test-project",
        "sub": "uid-1",
        "email": "Alice@DGU.ac.kr",
        "name": "Alice",
    }
    return claims | overrides


async def test_valid_firebase_token(
    monkeypatch: pytest.MonkeyPatch, project_settings: None
) -> None:
    monkeypatch.setattr(firebase, "_verify", lambda token, project_id: fake_claims())

    identity = await firebase.verify_id_token("token")

    assert identity == firebase.FirebaseIdentity(
        uid="uid-1", email="alice@dgu.ac.kr", name="Alice", picture_url=None
    )


async def test_invalid_firebase_token_is_unauthorized(
    monkeypatch: pytest.MonkeyPatch, project_settings: None
) -> None:
    def raise_invalid(token: str, project_id: str) -> dict[str, object]:
        raise ValueError("Token expired")

    monkeypatch.setattr(firebase, "_verify", raise_invalid)

    with pytest.raises(UnauthorizedException):
        await firebase.verify_id_token("token")


async def test_token_from_other_project_is_unauthorized(
    monkeypatch: pytest.MonkeyPatch, project_settings: None
) -> None:
    other = fake_claims(iss="https://securetoken.google.com/other-project")
    monkeypatch.setattr(firebase, "_verify", lambda token, project_id: other)

    with pytest.raises(UnauthorizedException):
        await firebase.verify_id_token("token")


def test_settings_parse_comma_lists_and_db_url() -> None:
    settings = Settings(
        admin_emails="Admin@DGU.ac.kr, b@dgu.ac.kr",  # type: ignore[arg-type]
        database_url="  postgresql://u:p@host/db?sslmode=require&channel_binding=require\n",
    )

    assert settings.admin_emails == ["admin@dgu.ac.kr", "b@dgu.ac.kr"]
    assert settings.database_url == "postgresql+asyncpg://u:p@host/db?ssl=require"
    assert Settings(database_url="").database_url.startswith("sqlite+aiosqlite")
