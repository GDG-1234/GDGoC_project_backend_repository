from functools import lru_cache
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CommaList = Annotated[list[str], NoDecode]
LOCAL_DATABASE_URL = "sqlite+aiosqlite:///./local.db"


class Settings(BaseSettings):
    """`.env` 또는 환경변수에서 읽는 설정. 항목 설명은 `.env.example` 참고."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = LOCAL_DATABASE_URL
    firebase_project_id: str = ""
    admin_emails: CommaList = []
    allowed_email_domains: CommaList = []
    cors_origins: CommaList = ["http://localhost:5173"]

    # skill(프로그램) 공통 틀
    service_api_key: str = ""
    tool_timeout_seconds: float = 10
    result_ttl_seconds: float = 1800
    result_store_max_items: int = 1000

    # 채팅
    daily_message_limit: int = 50  # 1인당 하루(한국 시간) 보낼 수 있는 메시지 수
    chat_history_limit: int = 20  # AI에 넘길 최근 메시지 수 (새 메시지 포함)

    @field_validator("admin_emails", "allowed_email_domains", "cors_origins", mode="before")
    @classmethod
    def split_comma(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("admin_emails", "allowed_email_domains")
    @classmethod
    def lowercase(cls, value: list[str]) -> list[str]:
        return [item.lower() for item in value]

    @field_validator("database_url")
    @classmethod
    def use_async_driver(cls, value: str) -> str:
        value = value.strip()  # 비밀값을 붙여 넣을 때 섞인 공백·줄바꿈 제거
        if not value:
            return LOCAL_DATABASE_URL
        # Neon, Supabase가 주는 `postgresql://...?sslmode=require` 주소를 asyncpg용으로 바꾼다.
        if value.startswith(("postgresql://", "postgres://")):
            value = "postgresql+asyncpg://" + value.split("://", 1)[1]
        if value.startswith("postgresql+asyncpg://"):
            parts = urlsplit(value)
            query = [
                ("ssl" if key == "sslmode" else key, val)
                for key, val in parse_qsl(parts.query)
                if key != "channel_binding"  # asyncpg가 모르는 옵션
            ]
            value = urlunsplit(parts._replace(query=urlencode(query)))
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
