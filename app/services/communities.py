from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.chat import (
    CHAT_TYPE_CHANNEL,
    CHAT_TYPE_GROUP,
    MEMBER_ROLE_ADMIN,
    MEMBER_ROLE_MEMBER,
    MEMBER_ROLE_OWNER,
    Chat,
)
from app.models.chat_member import ChatMember
from app.models.user import User
from app.repositories.chat_members import ChatMemberRepository
from app.repositories.chats import ChatRepository
from app.repositories.users import UserRepository
from app.schemas.community import (
    ChannelCreate,
    ChannelUpdate,
    CommunityCreate,
    CommunityUpdate,
    GroupCreate,
    GroupUpdate,
    MembersAdd,
)
from app.services.chats import ChatOverview, ChatService


class CommunityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.chats = ChatRepository(session)
        self.members = ChatMemberRepository(session)
        self.users = UserRepository(session)
        self.chat_service = ChatService(session)

    @staticmethod
    def _not_found(chat_type: str) -> HTTPException:
        label = "Group" if chat_type == CHAT_TYPE_GROUP else "Channel"
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")

    @staticmethod
    def _ensure_admin(membership: ChatMember | None) -> None:
        if membership is None or membership.role not in (
            MEMBER_ROLE_OWNER,
            MEMBER_ROLE_ADMIN,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

    @staticmethod
    def _ensure_owner(membership: ChatMember | None) -> None:
        if membership is None or membership.role != MEMBER_ROLE_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can perform this action",
            )

    async def _validate_member_ids(self, member_ids: list[UUID], owner_id: UUID) -> list[UUID]:
        unique_ids = list(dict.fromkeys(member_ids))
        unique_ids = [user_id for user_id in unique_ids if user_id != owner_id]
        users = await self.users.get_by_ids(set(unique_ids))
        missing = [user_id for user_id in unique_ids if user_id not in users]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Member not found: {missing[0]}",
            )
        return unique_ids

    async def _create(
        self,
        owner: User,
        payload: CommunityCreate,
        *,
        chat_type: str,
        is_public: bool,
    ) -> Chat:
        member_ids = await self._validate_member_ids(payload.member_ids, owner.id)
        chat = await self.chats.create_community(
            chat_type=chat_type,
            owner_id=owner.id,
            title=payload.title,
            description=payload.description,
            avatar_url=payload.avatar_url,
            is_public=is_public,
        )
        await self.members.add(chat.id, owner.id, MEMBER_ROLE_OWNER)
        joined_at = utcnow()
        for user_id in member_ids:
            await self.members.add(chat.id, user_id, MEMBER_ROLE_MEMBER, last_read_at=joined_at)
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def create_group(self, owner: User, payload: GroupCreate) -> Chat:
        return await self._create(owner, payload, chat_type=CHAT_TYPE_GROUP, is_public=False)

    async def create_channel(self, owner: User, payload: ChannelCreate) -> Chat:
        return await self._create(
            owner, payload, chat_type=CHAT_TYPE_CHANNEL, is_public=payload.is_public
        )

    async def get(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        *,
        allow_public: bool = False,
    ) -> tuple[Chat, ChatMember | None]:
        chat = await self.chats.get_by_id(chat_id)
        if chat is None or chat.chat_type != chat_type:
            raise self._not_found(chat_type)

        membership = await self.members.get(chat.id, current_user.id)
        if membership is not None:
            return chat, membership

        if allow_public and chat_type == CHAT_TYPE_CHANNEL and chat.is_public:
            return chat, None
        raise self._not_found(chat_type)

    async def list_overviews(self, current_user: User, chat_type: str) -> list[ChatOverview]:
        return await self.chat_service.list_overviews(current_user, chat_type)

    async def detail(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        *,
        allow_public: bool = False,
    ) -> tuple[ChatOverview, list[ChatMember], dict[UUID, User]]:
        chat, membership = await self.get(
            current_user, chat_id, chat_type, allow_public=allow_public
        )
        overview = await self.chat_service.build_overview(current_user, chat, membership)
        rows = await self.members.members_with_users(chat.id)
        return (
            overview,
            [member for member, _ in rows],
            {member.user_id: user for member, user in rows},
        )

    async def update(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        payload: CommunityUpdate | GroupUpdate | ChannelUpdate,
    ) -> Chat:
        chat, membership = await self.get(current_user, chat_id, chat_type)
        self._ensure_admin(membership)

        fields = payload.model_fields_set
        if "title" in fields and payload.title is not None:
            chat.title = payload.title
        if "description" in fields:
            chat.description = payload.description
        if "avatar_url" in fields:
            chat.avatar_url = payload.avatar_url
        if (
            chat_type == CHAT_TYPE_CHANNEL
            and isinstance(payload, ChannelUpdate)
            and "is_public" in fields
            and payload.is_public is not None
        ):
            chat.is_public = payload.is_public

        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def delete(self, current_user: User, chat_id: UUID, chat_type: str) -> None:
        chat, membership = await self.get(current_user, chat_id, chat_type)
        self._ensure_owner(membership)
        await self.session.delete(chat)
        await self.session.commit()

    async def add_members(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        payload: MembersAdd,
    ) -> None:
        chat, membership = await self.get(current_user, chat_id, chat_type)
        self._ensure_admin(membership)
        if payload.role == MEMBER_ROLE_ADMIN and membership.role != MEMBER_ROLE_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can grant admin rights",
            )

        user_ids = await self._validate_member_ids(payload.user_ids, chat.owner_id)
        existing = await self.members.member_ids(chat.id)
        joined_at = utcnow()
        for user_id in user_ids:
            if user_id in existing:
                continue
            await self.members.add(chat.id, user_id, payload.role, last_read_at=joined_at)
        await self.session.commit()

    async def _remove_member(self, chat: Chat, target_id: UUID, actor: ChatMember) -> None:
        target = await self.members.get(chat.id, target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        if target.role == MEMBER_ROLE_OWNER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The owner cannot leave or be removed",
            )
        if actor.role != MEMBER_ROLE_OWNER and target.role == MEMBER_ROLE_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot remove other admins",
            )
        await self.members.remove(chat.id, target_id)
        await self.session.commit()

    async def remove_member(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        target_id: UUID,
    ) -> None:
        chat, membership = await self.get(current_user, chat_id, chat_type)
        if target_id == current_user.id:
            await self._remove_member(chat, target_id, membership)
            return
        self._ensure_admin(membership)
        await self._remove_member(chat, target_id, membership)

    async def set_role(
        self,
        current_user: User,
        chat_id: UUID,
        chat_type: str,
        target_id: UUID,
        role: str,
    ) -> None:
        chat, membership = await self.get(current_user, chat_id, chat_type)
        self._ensure_owner(membership)
        target = await self.members.get(chat.id, target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        if target.role == MEMBER_ROLE_OWNER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The owner role cannot be changed",
            )
        await self.members.update_role(chat.id, target_id, role)
        await self.session.commit()

    async def subscribe(self, current_user: User, chat_id: UUID) -> Chat:
        chat = await self.chats.get_by_id(chat_id)
        if chat is None or chat.chat_type != CHAT_TYPE_CHANNEL:
            raise self._not_found(CHAT_TYPE_CHANNEL)

        existing = await self.members.get(chat.id, current_user.id)
        if existing is not None:
            return chat

        if not chat.is_public:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Channel is private",
            )

        await self.members.add(chat.id, current_user.id, MEMBER_ROLE_MEMBER, last_read_at=utcnow())
        await self.session.commit()
        return chat

    async def unsubscribe(self, current_user: User, chat_id: UUID) -> None:
        chat, membership = await self.get(current_user, chat_id, CHAT_TYPE_CHANNEL)
        await self._remove_member(chat, current_user.id, membership)
