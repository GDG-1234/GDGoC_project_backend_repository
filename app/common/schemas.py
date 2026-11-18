from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """모든 요청·응답 스키마의 베이스. JSON 필드 이름을 camelCase로 내보낸다."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ItemsResponse[T](CamelModel):
    """목록 응답은 `{ "items": [...] }`로 감싼다 (API 명세서 1.4)."""

    items: list[T]
