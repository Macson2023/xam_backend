from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import ChatMemberPublic, ChatPublic


def _strip_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("title must not be empty")
    return value


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class CommunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=2048)
    member_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _strip_title(value)

    @field_validator("description", "avatar_url")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class GroupCreate(CommunityCreate):
    pass


class ChannelCreate(CommunityCreate):
    is_public: bool = True


class CommunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=2048)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip_title(value)

    @field_validator("description", "avatar_url")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class GroupUpdate(CommunityUpdate):
    pass


class ChannelUpdate(CommunityUpdate):
    is_public: bool | None = None


class MembersAdd(BaseModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=100)
    role: Literal["admin", "member"] = "member"


class MemberRoleUpdate(BaseModel):
    role: Literal["admin", "member"]


class GroupPublic(ChatPublic):
    type: Literal["group"] = "group"


class GroupDetail(GroupPublic):
    members: list[ChatMemberPublic] = Field(default_factory=list)


class ChannelPublic(ChatPublic):
    type: Literal["channel"] = "channel"


class ChannelDetail(ChannelPublic):
    members: list[ChatMemberPublic] = Field(default_factory=list)
