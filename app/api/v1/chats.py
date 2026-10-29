from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.realtime import manager, new_message_event
from app.schemas.chat import ChatCreate, ChatPublic
from app.schemas.message import MessageCreate, MessagePage, MessagePublic
from app.schemas.user import UserPublic
from app.services.chats import ChatOverview, ChatService
from app.services.messages import MessageService

router = APIRouter(prefix="/chats", tags=["chats"])


def to_chat_public(overview: ChatOverview) -> ChatPublic:
    return ChatPublic(
        id=overview.chat.id,
        partner=UserPublic.model_validate(overview.partner),
        created_at=overview.chat.created_at,
        last_activity=overview.last_activity,
        unread_count=overview.unread_count,
        last_message=(
            MessagePublic.model_validate(overview.last_message)
            if overview.last_message is not None
            else None
        ),
    )


@router.post("", response_model=ChatPublic)
async def create_chat(
    payload: ChatCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ChatPublic:
    service = ChatService(session)
    chat = await service.get_or_create(current_user, payload.participant_id)
    overview = await service.build_overview(current_user, chat)
    return to_chat_public(overview)


@router.get("", response_model=list[ChatPublic])
async def list_chats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[ChatPublic]:
    overviews = await ChatService(session).list_overviews(current_user)
    return [to_chat_public(overview) for overview in overviews]


@router.post(
    "/{chat_id}/messages",
    response_model=MessagePublic,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    chat_id: UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePublic:
    message, chat = await MessageService(session).send(current_user, chat_id, payload)
    await manager.broadcast(chat.participant_ids(), new_message_event(message))
    return MessagePublic.model_validate(message)


@router.get("/{chat_id}/messages", response_model=MessagePage)
async def get_messages(
    chat_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessagePage:
    messages = await MessageService(session).history(
        current_user, chat_id, limit=limit, before=before
    )
    items = [MessagePublic.model_validate(message) for message in messages]
    next_cursor = items[-1].created_at if len(items) == limit else None
    return MessagePage(items=items, next_cursor=next_cursor)


@router.post("/{chat_id}/read", status_code=status.HTTP_200_OK)
async def mark_chat_read(
    chat_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    updated = await MessageService(session).mark_read(current_user, chat_id)
    return {"updated": updated}
