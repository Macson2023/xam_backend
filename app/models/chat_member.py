from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

from .chat import MEMBER_ROLE_MEMBER


class ChatMember(Base):
    __tablename__ = "chat_members"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_chat_members_role"),
        Index("ix_chat_members_user_id", "user_id"),
    )

    chat_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(
        String(16),
        default=MEMBER_ROLE_MEMBER,
        server_default=MEMBER_ROLE_MEMBER,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
