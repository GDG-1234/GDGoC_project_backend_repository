from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """앱 설정. 환경 변수나 .env 파일에서 찾는다"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_api_key: str = Field(min_length=1)
    tool_timeout_seconds: float = 10
    result_ttl_seconds: float = 1800
    result_store_max_items: int = 1000

@lru_cache
def get_settings() -> type[Settings]:
    return Settings
