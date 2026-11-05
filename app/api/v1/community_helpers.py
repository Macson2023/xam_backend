from uuid import UUID

from app.api.v1.chats import to_chat_public
from app.models.chat_member import ChatMember
from app.models.user import User
from app.schemas.chat import ChatMemberPublic
from app.schemas.community import ChannelDetail, ChannelPublic, GroupDetail, GroupPublic
from app.schemas.user import UserPublic
from app.services.chats import ChatOverview


def to_member_public(member: ChatMember, user: User) -> ChatMemberPublic:
    return ChatMemberPublic(
        user=UserPublic.model_validate(user),
        role=member.role,
        joined_at=member.joined_at,
        last_read_at=member.last_read_at,
    )


def to_group_public(overview: ChatOverview) -> GroupPublic:
    return GroupPublic(**to_chat_public(overview).model_dump())


def to_channel_public(overview: ChatOverview) -> ChannelPublic:
    return ChannelPublic(**to_chat_public(overview).model_dump())


def to_group_detail(
    overview: ChatOverview,
    members: list[ChatMember],
    users: dict[UUID, User],
) -> GroupDetail:
    return GroupDetail(
        **to_group_public(overview).model_dump(),
        members=[
            to_member_public(member, users[member.user_id])
            for member in members
            if member.user_id in users
        ],
    )


def to_channel_detail(
    overview: ChatOverview,
    members: list[ChatMember],
    users: dict[UUID, User],
) -> ChannelDetail:
    return ChannelDetail(
        **to_channel_public(overview).model_dump(),
        members=[
            to_member_public(member, users[member.user_id])
            for member in members
            if member.user_id in users
        ],
    )
