from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.message import MessagePublic
from app.schemas.user import UserPublic


class ChatCreate(BaseModel):
    participant_id: UUID


class ChatPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner: UserPublic
    created_at: datetime
    last_activity: datetime
    unread_count: int = 0
    last_message: MessagePublic | None = None
