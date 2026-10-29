from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_message_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be empty")
        return value


class MessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    sender_id: UUID
    content: str
    client_message_id: UUID | None = None
    created_at: datetime
    is_read: bool


class MessagePage(BaseModel):
    items: list[MessagePublic]
    next_cursor: datetime | None = None
