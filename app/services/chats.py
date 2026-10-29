from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.message import Message
from app.models.user import User
from app.repositories.chats import ChatRepository
from app.repositories.users import UserRepository

CHAT_NOT_FOUND = "Chat not found"


@dataclass(frozen=True)
class ChatOverview:
    chat: Chat
    partner: User
    last_message: Message | None
    unread_count: int
    last_activity: datetime


def ordered_pair(first: UUID, second: UUID) -> tuple[UUID, UUID]:
    return (first, second) if first < second else (second, first)


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chats = ChatRepository(session)
        self.users = UserRepository(session)

    async def get_or_create(self, current_user: User, participant_id: UUID) -> Chat:
        if participant_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create a chat with yourself",
            )

        if await self.users.get_by_id(participant_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
            )

        user1_id, user2_id = ordered_pair(current_user.id, participant_id)
        chat = await self.chats.get_between(user1_id, user2_id)
        if chat is not None:
            return chat

        try:
            chat = await self.chats.create(user1_id, user2_id)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            chat = await self.chats.get_between(user1_id, user2_id)
            if chat is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Chat already exists"
                ) from exc
        return chat

    async def get_participant_chat(self, current_user: User, chat_id: UUID) -> Chat:
        chat = await self.chats.get_by_id(chat_id)
        if chat is None or current_user.id not in chat.participant_ids():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAT_NOT_FOUND)
        return chat

    async def build_overview(self, current_user: User, chat: Chat) -> ChatOverview:
        last_messages = await self.chats.last_messages([chat.id])
        unread_counts = await self.chats.unread_counts([chat.id], current_user.id)
        partner_id = chat.partner_id(current_user.id)
        partners = await self.chats.users_by_ids({partner_id})

        partner = partners.get(partner_id)
        if partner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found"
            )

        last_message = last_messages.get(chat.id)
        return ChatOverview(
            chat=chat,
            partner=partner,
            last_message=last_message,
            unread_count=unread_counts.get(chat.id, 0),
            last_activity=last_message.created_at if last_message else chat.created_at,
        )

    async def list_overviews(self, current_user: User) -> list[ChatOverview]:
        chats = await self.chats.list_for_user(current_user.id)
        if not chats:
            return []

        chat_ids = [chat.id for chat in chats]
        partner_ids = {chat.partner_id(current_user.id) for chat in chats}
        last_messages = await self.chats.last_messages(chat_ids)
        unread_counts = await self.chats.unread_counts(chat_ids, current_user.id)
        partners = await self.chats.users_by_ids(partner_ids)

        overviews: list[ChatOverview] = []
        for chat in chats:
            partner = partners.get(chat.partner_id(current_user.id))
            if partner is None:
                continue
            last_message = last_messages.get(chat.id)
            overviews.append(
                ChatOverview(
                    chat=chat,
                    partner=partner,
                    last_message=last_message,
                    unread_count=unread_counts.get(chat.id, 0),
                    last_activity=last_message.created_at if last_message else chat.created_at,
                )
            )

        overviews.sort(key=lambda item: item.last_activity, reverse=True)
        return overviews
