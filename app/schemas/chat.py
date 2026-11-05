from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.message import MessagePublic
from app.schemas.user import UserPublic

ChatType = Literal["direct", "group", "channel"]
MemberRole = Literal["owner", "admin", "member"]


class ChatCreate(BaseModel):
    participant_id: UUID


class ChatMemberPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserPublic
    role: MemberRole
    joined_at: datetime
    last_read_at: datetime | None = None


class ChatPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ChatType
    partner: UserPublic | None = None
    title: str | None = None
    description: str | None = None
    avatar_url: str | None = None
    owner_id: UUID | None = None
    is_public: bool = False
    member_count: int = 0
    my_role: MemberRole | None = None
    created_at: datetime
    last_activity: datetime
    unread_count: int = 0
    last_message: MessagePublic | None = None
