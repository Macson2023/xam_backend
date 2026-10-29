from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    display_name: str
    avatar_url: str | None = None
    created_at: datetime
    last_seen: datetime | None = None
