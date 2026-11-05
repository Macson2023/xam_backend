from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import CHAT_TYPE_DIRECT, Chat
from app.models.chat_member import ChatMember
from app.models.message import Message
from app.models.user import User


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, chat_id: UUID) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def get_between(self, user1_id: UUID, user2_id: UUID) -> Chat | None:
        stmt = select(Chat).where(
            Chat.chat_type == CHAT_TYPE_DIRECT,
            Chat.user1_id == user1_id,
            Chat.user2_id == user2_id,
        )
        return await self.session.scalar(stmt)

    async def create(
        self,
        user1_id: UUID,
        user2_id: UUID,
    ) -> Chat:
        chat = Chat(
            chat_type=CHAT_TYPE_DIRECT,
            user1_id=user1_id,
            user2_id=user2_id,
        )
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def create_community(
        self,
        *,
        chat_type: str,
        owner_id: UUID,
        title: str,
        description: str | None,
        avatar_url: str | None = None,
        is_public: bool = False,
    ) -> Chat:
        chat = Chat(
            chat_type=chat_type,
            owner_id=owner_id,
            title=title,
            description=description,
            avatar_url=avatar_url,
            is_public=is_public,
        )
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def list_for_user(self, user_id: UUID, chat_type: str | None = None) -> list[Chat]:
        member_chat_ids = select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
        stmt = select(Chat).where(
            or_(
                Chat.user1_id == user_id,
                Chat.user2_id == user_id,
                Chat.id.in_(member_chat_ids),
            )
        )
        if chat_type is not None:
            stmt = stmt.where(Chat.chat_type == chat_type)
        stmt = stmt.order_by(Chat.created_at.desc())
        result = await self.session.scalars(stmt)
        return list(result)

    async def last_messages(self, chat_ids: list[UUID]) -> dict[UUID, Message]:
        if not chat_ids:
            return {}

        row_number = (
            func.row_number()
            .over(
                partition_by=Message.chat_id,
                order_by=(Message.created_at.desc(), Message.id.desc()),
            )
            .label("rn")
        )
        ranked = select(Message.id, row_number).where(Message.chat_id.in_(chat_ids)).subquery()
        stmt = select(Message).join(ranked, Message.id == ranked.c.id).where(ranked.c.rn == 1)
        messages = await self.session.scalars(stmt)
        return {message.chat_id: message for message in messages}

    async def unread_counts(self, chat_ids: list[UUID], user_id: UUID) -> dict[UUID, int]:
        if not chat_ids:
            return {}

        stmt = (
            select(Message.chat_id, func.count(Message.id))
            .where(
                Message.chat_id.in_(chat_ids),
                Message.sender_id != user_id,
                Message.is_read.is_(False),
            )
            .group_by(Message.chat_id)
        )
        rows = await self.session.execute(stmt)
        return {chat_id: count for chat_id, count in rows.all()}

    async def community_unread_counts(self, chat_ids: list[UUID], user_id: UUID) -> dict[UUID, int]:
        """Unread counts for group/channel chats based on per-member last_read_at."""
        if not chat_ids:
            return {}

        stmt = (
            select(Message.chat_id, func.count(Message.id))
            .join(ChatMember, ChatMember.chat_id == Message.chat_id)
            .where(
                ChatMember.user_id == user_id,
                Message.chat_id.in_(chat_ids),
                Message.sender_id != user_id,
                or_(
                    ChatMember.last_read_at.is_(None),
                    Message.created_at > ChatMember.last_read_at,
                ),
            )
            .group_by(Message.chat_id)
        )
        rows = await self.session.execute(stmt)
        return {chat_id: count for chat_id, count in rows.all()}

    async def count_unread_since(self, chat_id: UUID, user_id: UUID, since: datetime | None) -> int:
        stmt = select(func.count(Message.id)).where(
            Message.chat_id == chat_id,
            Message.sender_id != user_id,
        )
        if since is not None:
            stmt = stmt.where(Message.created_at > since)
        return await self.session.scalar(stmt) or 0

    async def partner_ids_for_user(self, user_id: UUID) -> set[UUID]:
        stmt = select(Chat.user1_id, Chat.user2_id).where(
            Chat.chat_type == CHAT_TYPE_DIRECT,
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
        )
        rows = await self.session.execute(stmt)
        partner_ids: set[UUID] = set()
        for user1_id, user2_id in rows.all():
            partner_ids.add(user2_id if user1_id == user_id else user1_id)
        return partner_ids

    async def users_by_ids(self, user_ids: set[UUID]) -> dict[UUID, User]:
        if not user_ids:
            return {}
        users = await self.session.scalars(select(User).where(User.id.in_(user_ids)))
        return {user.id: user for user in users}
