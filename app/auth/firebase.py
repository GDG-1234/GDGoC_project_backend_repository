from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import cachecontrol
import google.auth.transport.requests
import requests
from google.oauth2 import id_token
from starlette.concurrency import run_in_threadpool

from app.common.exceptions import UnauthorizedException
from app.core.config import get_settings


@dataclass(frozen=True)
class FirebaseIdentity:
    """검증된 Firebase ID 토큰에서 꺼낸 사용자 정보."""

    uid: str
    email: str
    name: str | None
    picture_url: str | None


@lru_cache
def _cached_request() -> google.auth.transport.requests.Request:
    # Google 공개키를 캐시해서 요청마다 다시 받지 않는다 (firebase-admin과 같은 방식).
    session = cachecontrol.CacheControl(requests.Session())
    return google.auth.transport.requests.Request(session=session)


def _verify(token: str, project_id: str) -> dict[str, Any]:
    return id_token.verify_firebase_token(token, _cached_request(), audience=project_id)


async def verify_id_token(token: str) -> FirebaseIdentity:
    """프론트가 보낸 Firebase ID 토큰을 검증한다. 잘못되거나 만료되면 401.

    서명·만료·audience(프로젝트 ID)·issuer를 확인한다. 서비스 계정 키는 필요 없다.
    """
    project_id = get_settings().firebase_project_id
    if not project_id:
        raise RuntimeError("FIREBASE_PROJECT_ID 설정이 필요합니다.")

    try:
        claims = await run_in_threadpool(_verify, token, project_id)
    except ValueError as exc:
        raise UnauthorizedException("유효하지 않은 로그인 토큰입니다.") from exc

    if claims.get("iss") != f"https://securetoken.google.com/{project_id}" or not claims.get("sub"):
        raise UnauthorizedException("유효하지 않은 로그인 토큰입니다.")

    email = claims.get("email")
    if not email:
        raise UnauthorizedException("이메일 정보가 없는 계정입니다.")
    return FirebaseIdentity(
        uid=claims["sub"],
        email=email.lower(),
        name=claims.get("name"),
        picture_url=claims.get("picture"),
    )
