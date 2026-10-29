from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow

MESSAGE_TYPE_TEXT = "text"
MESSAGE_TYPE_IMAGE = "image"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "chat_id", "sender_id", "client_message_id", name="uq_messages_client_message_id"
        ),
        CheckConstraint("message_type IN ('text', 'image')", name="ck_messages_type"),
        CheckConstraint(
            "message_type != 'image' OR image_url IS NOT NULL",
            name="ck_messages_image_requires_url",
        ),
        Index("idx_messages_chat_created", "chat_id", text("created_at DESC")),
        Index("ix_messages_chat_id", "chat_id"),
        Index("ix_messages_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chat_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    client_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    message_type: Mapped[str] = mapped_column(
        String(16), default=MESSAGE_TYPE_TEXT, server_default=MESSAGE_TYPE_TEXT, nullable=False
    )
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
