from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import (
    CHAT_TYPE_CHANNEL,
    MEMBER_ROLE_ADMIN,
    MEMBER_ROLE_OWNER,
    Chat,
)
from app.models.chat_member import ChatMember
from app.models.message import Message
from app.models.user import User
from app.repositories.chat_members import ChatMemberRepository
from app.repositories.chats import ChatRepository
from app.repositories.users import UserRepository

CHAT_NOT_FOUND = "Chat not found"


@dataclass(frozen=True)
class ChatOverview:
    chat: Chat
    partner: User | None
    last_message: Message | None
    unread_count: int
    last_activity: datetime
    my_role: str | None = None
    member_count: int = 0


def ordered_pair(first: UUID, second: UUID) -> tuple[UUID, UUID]:
    return (first, second) if first < second else (second, first)


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chats = ChatRepository(session)
        self.members = ChatMemberRepository(session)
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

    async def get_member_chat(
        self,
        current_user: User,
        chat_id: UUID,
        *,
        expected_type: str | None = None,
    ) -> tuple[Chat, ChatMember | None]:
        chat = await self.chats.get_by_id(chat_id)
        if chat is None or (expected_type is not None and chat.chat_type != expected_type):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAT_NOT_FOUND)

        if chat.is_direct():
            if current_user.id not in chat.participant_ids():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAT_NOT_FOUND)
            return chat, None

        membership = await self.members.get(chat.id, current_user.id)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CHAT_NOT_FOUND)
        return chat, membership

    async def get_participant_chat(
        self, current_user: User, chat_id: UUID, *, expected_type: str | None = None
    ) -> Chat:
        chat, _ = await self.get_member_chat(current_user, chat_id, expected_type=expected_type)
        return chat

    def ensure_can_post(self, chat: Chat, membership: ChatMember | None) -> None:
        if chat.chat_type != CHAT_TYPE_CHANNEL:
            return
        if membership is None or membership.role not in (
            MEMBER_ROLE_OWNER,
            MEMBER_ROLE_ADMIN,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only channel admins can post messages",
            )

    async def recipient_ids(self, chat: Chat) -> set[UUID]:
        if chat.is_direct():
            return set(chat.participant_ids())
        return await self.members.member_ids(chat.id)

    async def build_overview(
        self,
        current_user: User,
        chat: Chat,
        membership: ChatMember | None = None,
    ) -> ChatOverview:
        last_messages = await self.chats.last_messages([chat.id])

        if chat.is_direct():
            unread_counts = await self.chats.unread_counts([chat.id], current_user.id)
            partner_id = chat.partner_id(current_user.id)
            partners = await self.chats.users_by_ids({partner_id} if partner_id else set())
            partner = partners.get(partner_id) if partner_id is not None else None
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
                member_count=2,
            )

        if membership is None:
            membership = await self.members.get(chat.id, current_user.id)
        unread_counts = await self.chats.community_unread_counts([chat.id], current_user.id)
        member_count = await self.members.count_for_chat(chat.id)
        last_message = last_messages.get(chat.id)
        return ChatOverview(
            chat=chat,
            partner=None,
            last_message=last_message,
            unread_count=unread_counts.get(chat.id, 0),
            last_activity=last_message.created_at if last_message else chat.created_at,
            my_role=membership.role if membership else None,
            member_count=member_count,
        )

    async def list_overviews(
        self, current_user: User, chat_type: str | None = None
    ) -> list[ChatOverview]:
        chats = await self.chats.list_for_user(current_user.id, chat_type)
        if not chats:
            return []
        return await self.overviews_for_chats(current_user, chats)

    async def overviews_for_chats(
        self, current_user: User, chats: list[Chat]
    ) -> list[ChatOverview]:
        if not chats:
            return []

        chat_ids = [chat.id for chat in chats]
        direct_chats = [chat for chat in chats if chat.is_direct()]
        community_chats = [chat for chat in chats if not chat.is_direct()]
        community_ids = [chat.id for chat in community_chats]

        partner_ids = {
            partner_id
            for chat in direct_chats
            if (partner_id := chat.partner_id(current_user.id)) is not None
        }
        last_messages = await self.chats.last_messages(chat_ids)
        unread_counts = await self.chats.unread_counts(
            [chat.id for chat in direct_chats], current_user.id
        )
        unread_counts.update(
            await self.chats.community_unread_counts(community_ids, current_user.id)
        )
        partners = await self.chats.users_by_ids(partner_ids)
        memberships = await self.members.memberships_for_user(current_user.id)
        member_counts = await self.members.member_counts(community_ids)

        overviews: list[ChatOverview] = []
        for chat in chats:
            last_message = last_messages.get(chat.id)
            last_activity = last_message.created_at if last_message else chat.created_at
            if chat.is_direct():
                partner_id = chat.partner_id(current_user.id)
                partner = partners.get(partner_id) if partner_id is not None else None
                if partner is None:
                    continue
                overviews.append(
                    ChatOverview(
                        chat=chat,
                        partner=partner,
                        last_message=last_message,
                        unread_count=unread_counts.get(chat.id, 0),
                        last_activity=last_activity,
                        member_count=2,
                    )
                )
            else:
                membership = memberships.get(chat.id)
                overviews.append(
                    ChatOverview(
                        chat=chat,
                        partner=None,
                        last_message=last_message,
                        unread_count=unread_counts.get(chat.id, 0),
                        last_activity=last_activity,
                        my_role=membership.role if membership else None,
                        member_count=member_counts.get(chat.id, 0),
                    )
                )

        overviews.sort(key=lambda item: item.last_activity, reverse=True)
        return overviews
