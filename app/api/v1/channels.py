from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.community_helpers import (
    to_channel_detail,
    to_channel_public,
    to_member_public,
)
from app.db.session import get_db
from app.models.chat import CHAT_TYPE_CHANNEL
from app.models.user import User
from app.realtime import manager, new_message_event
from app.schemas.chat import ChatMemberPublic
from app.schemas.community import (
    ChannelCreate,
    ChannelDetail,
    ChannelPublic,
    ChannelUpdate,
    MemberRoleUpdate,
    MembersAdd,
)
from app.schemas.message import MessageCreate, MessagePage, MessagePublic
from app.services.chats import ChatService
from app.services.communities import CommunityService
from app.services.messages import MessageService

router = APIRouter(prefix="/channels", tags=["channels"])


@router.post("", response_model=ChannelPublic, status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChannelCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelPublic:
    service = CommunityService(session)
    chat = await service.create_channel(current_user, payload)
    overview = await ChatService(session).build_overview(current_user, chat)
    return to_channel_public(overview)


@router.get("", response_model=list[ChannelPublic])
async def list_channels(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ChannelPublic]:
    overviews = await CommunityService(session).list_overviews(current_user, CHAT_TYPE_CHANNEL)
    return [to_channel_public(overview) for overview in overviews]


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelDetail:
    overview, members, users = await CommunityService(session).detail(
        current_user, channel_id, CHAT_TYPE_CHANNEL, allow_public=True
    )
    return to_channel_detail(overview, members, users)


@router.patch("/{channel_id}", response_model=ChannelPublic)
async def update_channel(
    channel_id: UUID,
    payload: ChannelUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelPublic:
    service = CommunityService(session)
    chat = await service.update(current_user, channel_id, CHAT_TYPE_CHANNEL, payload)
    overview = await ChatService(session).build_overview(current_user, chat)
    return to_channel_public(overview)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).delete(current_user, channel_id, CHAT_TYPE_CHANNEL)


@router.post("/{channel_id}/subscribe", response_model=ChannelDetail)
async def subscribe_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelDetail:
    service = CommunityService(session)
    await service.subscribe(current_user, channel_id)
    overview, members, users = await service.detail(current_user, channel_id, CHAT_TYPE_CHANNEL)
    return to_channel_detail(overview, members, users)


@router.post("/{channel_id}/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).unsubscribe(current_user, channel_id)


@router.get("/{channel_id}/members", response_model=list[ChatMemberPublic])
async def list_channel_members(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ChatMemberPublic]:
    _, members, users = await CommunityService(session).detail(
        current_user, channel_id, CHAT_TYPE_CHANNEL, allow_public=True
    )
    return [
        to_member_public(member, users[member.user_id])
        for member in members
        if member.user_id in users
    ]


@router.post(
    "/{channel_id}/members",
    response_model=ChannelDetail,
    status_code=status.HTTP_201_CREATED,
)
async def add_channel_members(
    channel_id: UUID,
    payload: MembersAdd,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelDetail:
    service = CommunityService(session)
    await service.add_members(current_user, channel_id, CHAT_TYPE_CHANNEL, payload)
    overview, members, users = await service.detail(current_user, channel_id, CHAT_TYPE_CHANNEL)
    return to_channel_detail(overview, members, users)


@router.patch("/{channel_id}/members/{user_id}", response_model=ChannelDetail)
async def update_channel_member_role(
    channel_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChannelDetail:
    service = CommunityService(session)
    await service.set_role(current_user, channel_id, CHAT_TYPE_CHANNEL, user_id, payload.role)
    overview, members, users = await service.detail(current_user, channel_id, CHAT_TYPE_CHANNEL)
    return to_channel_detail(overview, members, users)


@router.delete("/{channel_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_member(
    channel_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).remove_member(
        current_user, channel_id, CHAT_TYPE_CHANNEL, user_id
    )


@router.post(
    "/{channel_id}/messages",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_channel_message(
    channel_id: UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send(
        current_user, channel_id, payload, expected_type=CHAT_TYPE_CHANNEL
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.post(
    "/{channel_id}/images",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_channel_image(
    channel_id: UUID,
    file: Annotated[UploadFile, File(description="Image file")],
    caption: Annotated[str | None, Form(max_length=4000)] = None,
    client_message_id: Annotated[UUID | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send_image(
        current_user,
        channel_id,
        file,
        caption=caption,
        client_message_id=client_message_id,
        expected_type=CHAT_TYPE_CHANNEL,
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.get("/{channel_id}/messages", response_model=MessagePage)
async def get_channel_messages(
    channel_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePage:
    messages = await MessageService(session).history(
        current_user,
        channel_id,
        limit=limit,
        before=before,
        expected_type=CHAT_TYPE_CHANNEL,
    )
    items = [MessagePublic.model_validate(message) for message in messages]
    next_cursor = items[-1].created_at if len(items) == limit else None
    return MessagePage(items=items, next_cursor=next_cursor)


@router.post("/{channel_id}/read", status_code=status.HTTP_200_OK)
async def mark_channel_read(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    updated = await MessageService(session).mark_read(
        current_user, channel_id, expected_type=CHAT_TYPE_CHANNEL
    )
    return {"updated": updated}
