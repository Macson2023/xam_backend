from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("user1_id < user2_id", name="ck_chats_user_order"),
        UniqueConstraint("user1_id", "user2_id", name="uq_chats_user_pair"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user1_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user2_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    def participant_ids(self) -> tuple[UUID, UUID]:
        return self.user1_id, self.user2_id

    def partner_id(self, user_id: UUID) -> UUID:
        return self.user2_id if self.user1_id == user_id else self.user1_id
