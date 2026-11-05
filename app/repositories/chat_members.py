from datetime import datetime
from uuid import UUID

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_member import ChatMember
from app.models.user import User

ROLE_ORDER = case(
    (ChatMember.role == "owner", 0),
    (ChatMember.role == "admin", 1),
    else_=2,
)


class ChatMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, chat_id: UUID, user_id: UUID) -> ChatMember | None:
        return await self.session.get(ChatMember, (chat_id, user_id))

    async def add(
        self,
        chat_id: UUID,
        user_id: UUID,
        role: str = "member",
        *,
        last_read_at: datetime | None = None,
    ) -> ChatMember:
        member = await self.get(chat_id, user_id)
        if member is not None:
            return member
        member = ChatMember(
            chat_id=chat_id,
            user_id=user_id,
            role=role,
            last_read_at=last_read_at,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def list_for_chat(self, chat_id: UUID) -> list[ChatMember]:
        stmt = (
            select(ChatMember)
            .where(ChatMember.chat_id == chat_id)
            .order_by(ROLE_ORDER, ChatMember.joined_at)
        )
        result = await self.session.scalars(stmt)
        return list(result)

    async def members_with_users(self, chat_id: UUID) -> list[tuple[ChatMember, User]]:
        stmt = (
            select(ChatMember, User)
            .join(User, User.id == ChatMember.user_id)
            .where(ChatMember.chat_id == chat_id)
            .order_by(ROLE_ORDER, ChatMember.joined_at)
        )
        rows = await self.session.execute(stmt)
        return [(member, user) for member, user in rows.all()]

    async def member_ids(self, chat_id: UUID) -> set[UUID]:
        stmt = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
        return set(await self.session.scalars(stmt))

    async def member_counts(self, chat_ids: list[UUID]) -> dict[UUID, int]:
        if not chat_ids:
            return {}
        stmt = (
            select(ChatMember.chat_id, func.count(ChatMember.user_id))
            .where(ChatMember.chat_id.in_(chat_ids))
            .group_by(ChatMember.chat_id)
        )
        rows = await self.session.execute(stmt)
        return {chat_id: count for chat_id, count in rows.all()}

    async def count_for_chat(self, chat_id: UUID) -> int:
        stmt = select(func.count(ChatMember.user_id)).where(ChatMember.chat_id == chat_id)
        return await self.session.scalar(stmt) or 0

    async def memberships_for_user(self, user_id: UUID) -> dict[UUID, ChatMember]:
        stmt = select(ChatMember).where(ChatMember.user_id == user_id)
        members = await self.session.scalars(stmt)
        return {member.chat_id: member for member in members}

    async def user_ids_for_chats(self, chat_ids: list[UUID]) -> dict[UUID, set[UUID]]:
        if not chat_ids:
            return {}
        stmt = select(ChatMember.chat_id, ChatMember.user_id).where(
            ChatMember.chat_id.in_(chat_ids)
        )
        rows = await self.session.execute(stmt)
        result: dict[UUID, set[UUID]] = {}
        for chat_id, user_id in rows.all():
            result.setdefault(chat_id, set()).add(user_id)
        return result

    async def update_role(self, chat_id: UUID, user_id: UUID, role: str) -> None:
        stmt = (
            update(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .values(role=role)
        )
        await self.session.execute(stmt)

    async def mark_read(self, chat_id: UUID, user_id: UUID, read_at: datetime) -> None:
        stmt = (
            update(ChatMember)
            .where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
            .values(last_read_at=read_at)
        )
        await self.session.execute(stmt)

    async def remove(self, chat_id: UUID, user_id: UUID) -> None:
        stmt = delete(ChatMember).where(
            ChatMember.chat_id == chat_id, ChatMember.user_id == user_id
        )
        await self.session.execute(stmt)
