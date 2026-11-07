from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.community_helpers import (
    to_group_detail,
    to_group_public,
    to_member_public,
)
from app.db.session import get_db
from app.models.chat import CHAT_TYPE_GROUP
from app.models.user import User
from app.realtime import manager, new_message_event
from app.schemas.chat import ChatMemberPublic
from app.schemas.community import (
    GroupCreate,
    GroupDetail,
    GroupPublic,
    GroupUpdate,
    MemberRoleUpdate,
    MembersAdd,
)
from app.schemas.message import MessageCreate, MessagePage, MessagePublic
from app.services.chats import ChatService
from app.services.communities import CommunityService
from app.services.messages import MessageService

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=GroupPublic, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupPublic:
    service = CommunityService(session)
    chat = await service.create_group(current_user, payload)
    overview = await ChatService(session).build_overview(current_user, chat)
    return to_group_public(overview)


@router.get("", response_model=list[GroupPublic])
async def list_groups(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[GroupPublic]:
    overviews = await CommunityService(session).list_overviews(current_user, CHAT_TYPE_GROUP)
    return [to_group_public(overview) for overview in overviews]


@router.get("/{group_id}", response_model=GroupDetail)
async def get_group(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupDetail:
    overview, members, users = await CommunityService(session).detail(
        current_user, group_id, CHAT_TYPE_GROUP
    )
    return to_group_detail(overview, members, users)


@router.patch("/{group_id}", response_model=GroupPublic)
async def update_group(
    group_id: UUID,
    payload: GroupUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupPublic:
    service = CommunityService(session)
    chat = await service.update(current_user, group_id, CHAT_TYPE_GROUP, payload)
    overview = await ChatService(session).build_overview(current_user, chat)
    return to_group_public(overview)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).delete(current_user, group_id, CHAT_TYPE_GROUP)


@router.get("/{group_id}/members", response_model=list[ChatMemberPublic])
async def list_group_members(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ChatMemberPublic]:
    _, members, users = await CommunityService(session).detail(
        current_user, group_id, CHAT_TYPE_GROUP
    )
    return [
        to_member_public(member, users[member.user_id])
        for member in members
        if member.user_id in users
    ]


@router.post(
    "/{group_id}/members",
    response_model=GroupDetail,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_members(
    group_id: UUID,
    payload: MembersAdd,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupDetail:
    service = CommunityService(session)
    await service.add_members(current_user, group_id, CHAT_TYPE_GROUP, payload)
    overview, members, users = await service.detail(current_user, group_id, CHAT_TYPE_GROUP)
    return to_group_detail(overview, members, users)


@router.patch("/{group_id}/members/{user_id}", response_model=GroupDetail)
async def update_group_member_role(
    group_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GroupDetail:
    service = CommunityService(session)
    await service.set_role(current_user, group_id, CHAT_TYPE_GROUP, user_id, payload.role)
    overview, members, users = await service.detail(current_user, group_id, CHAT_TYPE_GROUP)
    return to_group_detail(overview, members, users)


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(
    group_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).remove_member(current_user, group_id, CHAT_TYPE_GROUP, user_id)


@router.post("/{group_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_group(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    await CommunityService(session).remove_member(
        current_user, group_id, CHAT_TYPE_GROUP, current_user.id
    )


@router.post(
    "/{group_id}/messages",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_group_message(
    group_id: UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send(
        current_user, group_id, payload, expected_type=CHAT_TYPE_GROUP
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.post(
    "/{group_id}/images",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_group_image(
    group_id: UUID,
    file: Annotated[UploadFile, File(description="Image file")],
    caption: Annotated[str | None, Form(max_length=4000)] = None,
    client_message_id: Annotated[UUID | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send_image(
        current_user,
        group_id,
        file,
        caption=caption,
        client_message_id=client_message_id,
        expected_type=CHAT_TYPE_GROUP,
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.post(
    "/{group_id}/audio",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_group_audio(
    group_id: UUID,
    file: Annotated[UploadFile, File(description="Audio file")],
    duration_seconds: Annotated[float | None, Form()] = None,
    client_message_id: Annotated[UUID | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send_audio(
        current_user,
        group_id,
        file,
        duration_seconds=duration_seconds,
        client_message_id=client_message_id,
        expected_type=CHAT_TYPE_GROUP,
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.post(
    "/{group_id}/video-notes",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_group_video_note(
    group_id: UUID,
    file: Annotated[UploadFile, File(description="Video note file")],
    duration_seconds: Annotated[float | None, Form()] = None,
    client_message_id: Annotated[UUID | None, Form()] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send_video_note(
        current_user,
        group_id,
        file,
        duration_seconds=duration_seconds,
        client_message_id=client_message_id,
        expected_type=CHAT_TYPE_GROUP,
    )
    recipients = await ChatService(session).recipient_ids(chat)
    await manager.broadcast(recipients, new_message_event(message))
    return MessagePublic.model_validate(message)


@router.get("/{group_id}/messages", response_model=MessagePage)
async def get_group_messages(
    group_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePage:
    messages = await MessageService(session).history(
        current_user,
        group_id,
        limit=limit,
        before=before,
        expected_type=CHAT_TYPE_GROUP,
    )
    items = [MessagePublic.model_validate(message) for message in messages]
    next_cursor = items[-1].created_at if len(items) == limit else None
    return MessagePage(items=items, next_cursor=next_cursor)


@router.post("/{group_id}/read", status_code=status.HTTP_200_OK)
async def mark_group_read(
    group_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    updated = await MessageService(session).mark_read(
        current_user, group_id, expected_type=CHAT_TYPE_GROUP
    )
    return {"updated": updated}
