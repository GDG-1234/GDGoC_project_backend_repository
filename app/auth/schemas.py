from datetime import datetime

from app.common.schemas import CamelModel


class UserResponse(CamelModel):
    id: int
    email: str
    name: str | None
    picture_url: str | None
    is_admin: bool
    created_at: datetime
