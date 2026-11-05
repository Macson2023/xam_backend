from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

CHAT_TYPE_DIRECT = "direct"
CHAT_TYPE_GROUP = "group"
CHAT_TYPE_CHANNEL = "channel"

MEMBER_ROLE_OWNER = "owner"
MEMBER_ROLE_ADMIN = "admin"
MEMBER_ROLE_MEMBER = "member"


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("user1_id < user2_id", name="ck_chats_user_order"),
        CheckConstraint("chat_type IN ('direct', 'group', 'channel')", name="ck_chats_type"),
        CheckConstraint(
            "(chat_type = 'direct' AND user1_id IS NOT NULL AND user2_id IS NOT NULL"
            " AND owner_id IS NULL)"
            " OR (chat_type <> 'direct' AND user1_id IS NULL AND user2_id IS NULL"
            " AND owner_id IS NOT NULL AND title IS NOT NULL)",
            name="ck_chats_shape",
        ),
        UniqueConstraint("user1_id", "user2_id", name="uq_chats_user_pair"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chat_type: Mapped[str] = mapped_column(
        String(16),
        default=CHAT_TYPE_DIRECT,
        server_default=CHAT_TYPE_DIRECT,
        nullable=False,
        index=True,
    )
    user1_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user2_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    def participant_ids(self) -> tuple[UUID, ...]:
        if self.user1_id is None or self.user2_id is None:
            return ()
        return self.user1_id, self.user2_id

    def partner_id(self, user_id: UUID) -> UUID | None:
        if self.chat_type != CHAT_TYPE_DIRECT:
            return None
        return self.user2_id if self.user1_id == user_id else self.user1_id

    def is_direct(self) -> bool:
        return self.chat_type == CHAT_TYPE_DIRECT
