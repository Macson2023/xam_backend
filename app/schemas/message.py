from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageType = Literal["text", "image"]


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
    message_type: MessageType = "text"
    image_url: str | None = None
    image_mime_type: str | None = None
    image_size_bytes: int | None = None
    client_message_id: UUID | None = None
    created_at: datetime
    is_read: bool

    @field_validator("message_type", mode="before")
    @classmethod
    def default_message_type(cls, value: object) -> object:
        return value or "text"


class MessagePage(BaseModel):
    items: list[MessagePublic]
    next_cursor: datetime | None = None
